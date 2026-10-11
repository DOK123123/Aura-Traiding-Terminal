"""Owner-protected read-only Demo routes; Binance routes stay separate."""
import os
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

router = APIRouter(prefix='/api/bybit-demo', tags=['Read-only Bybit Demo account'])
basic = HTTPBasic(auto_error=False)


def owner(request: Request, credentials: HTTPBasicCredentials | None = Depends(basic)):
    if not request.app.state.bybit_demo.configured:
        return
    # Reuse the existing owner-view password, not any exchange credential.
    password = os.getenv('AURA_TESTNET_VIEW_PASSWORD', '')
    if len(password) < 12:
        raise HTTPException(403, 'Просмотр Demo закрыт. Настройте AURA_TESTNET_VIEW_PASSWORD (от 12 символов).',
                            headers={'Cache-Control':'no-store'})
    if (credentials is None or not secrets.compare_digest(credentials.username.encode(), b'aura')
            or not secrets.compare_digest(credentials.password.encode(), password.encode())):
        raise HTTPException(401, 'Требуется вход владельца для просмотра Demo.',
                            headers={'WWW-Authenticate':'Basic realm="Aura Bybit Demo", charset="UTF-8"', 'Cache-Control':'no-store'})


@router.get('/login', dependencies=[Depends(owner)])
def login():
    return RedirectResponse('/', status_code=303, headers={'Cache-Control':'no-store'})


async def read(request, section, symbol, category):
    result = await request.app.state.bybit_demo.read(section, symbol, category)
    return JSONResponse(result, headers={'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})


@router.get('/account', dependencies=[Depends(owner)])
async def account(request: Request, symbol: str = Query('BTCUSDT', pattern=r'^[A-Z0-9-]{3,64}$'),
                  category: Literal['spot', 'linear', 'inverse', 'option'] = 'spot'):
    return await read(request, 'account', symbol, category)


@router.get('/history', dependencies=[Depends(owner)])
async def history(request: Request, symbol: str = Query('BTCUSDT', pattern=r'^[A-Z0-9-]{3,64}$'),
                  category: Literal['spot', 'linear', 'inverse', 'option'] = 'spot'):
    return await read(request, 'history', symbol, category)

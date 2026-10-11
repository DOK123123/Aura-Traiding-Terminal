"""Owner-protected GET routes. Never exposes credentials or raw upstream errors."""
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

router = APIRouter(prefix='/api/testnet', tags=['Read-only Testnet account'])
basic = HTTPBasic(auto_error=False)


def owner(request: Request, credentials: HTTPBasicCredentials | None = Depends(basic)):
    if not request.app.state.testnet.configured:
        return
    password = os.getenv('AURA_TESTNET_VIEW_PASSWORD', '')
    if len(password) < 12:
        raise HTTPException(403, 'Просмотр аккаунта закрыт. Настройте AURA_TESTNET_VIEW_PASSWORD (от 12 символов).',
                            headers={'Cache-Control':'no-store'})
    if (credentials is None or not secrets.compare_digest(credentials.username.encode(), b'aura')
            or not secrets.compare_digest(credentials.password.encode(), password.encode())):
        raise HTTPException(401, 'Требуется вход владельца для просмотра Testnet.',
                            headers={'WWW-Authenticate':'Basic realm="Aura Testnet", charset="UTF-8"',
                                     'Cache-Control':'no-store'})


@router.get('/login', dependencies=[Depends(owner)])
def login():
    return RedirectResponse('/', status_code=303, headers={'Cache-Control':'no-store'})


async def read(request, section, symbol='BTCUSDT'):
    result = await request.app.state.testnet.read(section, symbol)
    return JSONResponse(result, headers={'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})


@router.get('/account', dependencies=[Depends(owner)])
async def account(request: Request):
    return await read(request, 'account')


@router.get('/history', dependencies=[Depends(owner)])
async def history(request: Request, symbol: str = Query('BTCUSDT', pattern=r'^[A-Z0-9]{5,20}$')):
    return await read(request, 'history', symbol)

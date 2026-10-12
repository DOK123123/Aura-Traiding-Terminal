"""Owner-only local ledger actions; authenticated GETs and same-origin protected writes."""
import os
import secrets
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, Field

from .models import PaperError

router = APIRouter(prefix='/api/paper',tags=['Virtual-only paper trading'])
basic = HTTPBasic(auto_error=False)
HEADERS = {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}


def owner(credentials: HTTPBasicCredentials | None = Depends(basic)):
    password = os.getenv('AURA_TESTNET_VIEW_PASSWORD','')
    if len(password) < 12:
        raise HTTPException(403,'Paper account закрыт: настройте пароль владельца AURA_TESTNET_VIEW_PASSWORD (от 12 символов).',headers=HEADERS)
    if (credentials is None or not secrets.compare_digest(credentials.username.encode(),b'aura')
            or not secrets.compare_digest(credentials.password.encode(),password.encode())):
        raise HTTPException(401,'Требуется вход владельца.',headers=dict(HEADERS,**{'WWW-Authenticate':'Basic realm="Aura Paper", charset="UTF-8"'}))


def mutation(request: Request, _: None = Depends(owner)):
    if request.headers.get('X-Aura-Paper') != 'local-only' or request.headers.get('Sec-Fetch-Site') == 'cross-site':
        raise HTTPException(403,'Запрос paper action отклонён.',headers=HEADERS)
    origin = request.headers.get('origin')
    if origin:
        try:
            parsed = urlsplit(origin)
            if (parsed.scheme not in ('http','https') or parsed.netloc.lower() != request.headers.get('host','').lower()
                    or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
                raise ValueError()
        except ValueError:
            raise HTTPException(403,'Запрос paper action отклонён.',headers=HEADERS) from None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class OpenPosition(StrictModel):
    request_id: StrictStr = Field(max_length=36)
    symbol: Literal['BTCUSDT']
    timeframe: Literal['1m','5m','15m','1h']
    direction: Literal['LONG','SHORT']
    expected_source: StrictStr = Field(min_length=1,max_length=120)
    expected_candle_time: StrictInt = Field(ge=0)
    expected_price: StrictStr = Field(min_length=1,max_length=42)
    position_size: StrictStr | None = Field(default=None,max_length=42)
    stop_loss: StrictStr | None = Field(default=None,max_length=42)
    take_profit: StrictStr | None = Field(default=None,max_length=42)
    entry_reason: StrictStr = Field(min_length=1,max_length=300)
    signal_id: StrictStr | None = Field(default=None,min_length=1,max_length=120)


class ClosePosition(StrictModel):
    request_id: StrictStr = Field(max_length=36)
    exit_reason: StrictStr = Field(min_length=1,max_length=300)


class Configuration(StrictModel):
    starting_balance: StrictStr = Field(max_length=42)
    commission_pct: StrictStr = Field(max_length=42)
    risk_per_trade_pct: StrictStr = Field(max_length=42)
    maximum_position_size_usdt: StrictStr = Field(max_length=42)
    maximum_simultaneous_positions: StrictInt
    stop_loss_pct: StrictStr = Field(max_length=42)
    take_profit_pct: StrictStr = Field(max_length=42)


MESSAGES = {
 'AUTO_PREFLIGHT_RISK':'Auto Paper activation blocked: saved risk must be at most 1% per trade. Save safe settings explicitly.',
 'AUTO_PREFLIGHT_POSITIONS':'Auto Paper activation blocked: saved maximum open positions must be 1, with no more than one existing open position.',
 'AUTO_PREFLIGHT_STOPS':'Auto Paper activation blocked: finite positive protective SL/TP on the correct LONG/SHORT entry sides are required.',
 'AUTO_PREFLIGHT_POLICY':'Auto Paper activation blocked: select SKIP or explicit PAPER_SETTINGS protective policy.',
 'AUTO_PREFLIGHT_VIRTUAL':'Auto Paper activation blocked: virtual-only execution boundary failed.',
 'STALE_DATA':'Данные устарели. Операция заблокирована.',
 'SOURCE_MISMATCH':'Источник не совпадает с графиком/позицией.',
 'QUOTE_CHANGED':'Закрытая свеча изменилась. Запросите новую paper quote.',
 'MARKET_GAP':'В истории свечей пропуск. Защитные paper exits приостановлены.',
 'MARKET_TIMEOUT':'Превышено время ожидания публичных котировок.',
 'MARKET_UNAVAILABLE':'Публичные котировки временно недоступны.',
 'STORAGE_UNAVAILABLE':'Журнал временно недоступен. Баланс не сброшен.',
 'CORRUPT_JOURNAL':'Проверка журнала не пройдена. Баланс не сброшен.',
 'INVALID_MARKET_DATA':'Рыночные данные некорректны.',
 'INSUFFICIENT_BALANCE':'Недостаточно свободных виртуальных средств.',
 'RISK_LIMIT':'Превышен риск на сделку с учётом комиссий.',
 'POSITION_LIMIT':'Достигнут лимит открытых позиций.',
 'POSITION_SIZE_LIMIT':'Превышен максимальный размер позиции в USDT.',
 'INVALID_STOPS':'Некорректные SL/TP или комиссия превышает доход до TP.',
 'STARTING_BALANCE_LOCKED':'Начальный баланс нельзя менять после первой сделки.',
 'IDEMPOTENCY_CONFLICT':'Этот request ID уже использован для другого действия.',
 'DUPLICATE_SIGNAL':'Этот signal ID уже обработан.',
 'POSITION_NOT_FOUND':'Paper-позиция не найдена.',
 'POSITION_CLOSED':'Paper-позиция уже закрыта.',
 'UNSUPPORTED_MARKET':'На этом этапе paper поддерживает BTCUSDT.',
 'INVALID_SETTINGS':'Некорректные настройки paper risk management.',
 'INVALID_DATA':'Некорректные данные.',
 'INVALID_REQUEST_ID':'Некорректный request ID.',
 'INVALID_POSITION_SIZE':'Количество должно быть положительным, до 12 знаков после точки.',
}


async def respond(operation):
    try:
        return JSONResponse(await operation,headers=HEADERS)
    except PaperError as error:
        code = error.code if error.code in MESSAGES else 'INVALID_DATA'
        status = 503 if code in ('STORAGE_UNAVAILABLE','CORRUPT_JOURNAL','MARKET_TIMEOUT','MARKET_UNAVAILABLE') else 409
        return JSONResponse({'paper':True,'real_money_execution':'DISABLED','code':code,'message':MESSAGES[code]},status_code=status,headers=HEADERS)


@router.get('/login',dependencies=[Depends(owner)])
def login():
    return RedirectResponse('/',status_code=303,headers=HEADERS)


@router.get('/state',dependencies=[Depends(owner)])
async def state(request:Request,scope:Literal['ALL','MANUAL','AUTO']='ALL'):
    return await respond(request.app.state.paper.state(scope))


@router.get('/quote',dependencies=[Depends(owner)])
async def quote(request:Request,symbol:Literal['BTCUSDT']='BTCUSDT',timeframe:Literal['1m','5m','15m','1h']='15m'):
    return await respond(request.app.state.paper.quote(symbol,timeframe))


@router.post('/positions/open',dependencies=[Depends(mutation)])
async def open_position(request:Request,body:OpenPosition):
    return await respond(request.app.state.paper.open(body.model_dump()))


@router.post('/positions/{trade_id}/close',dependencies=[Depends(mutation)])
async def close_position(trade_id:str,request:Request,body:ClosePosition):
    return await respond(request.app.state.paper.close_position(trade_id,body.model_dump()))


@router.post('/settings',dependencies=[Depends(mutation)])
async def settings(request:Request,body:Configuration):
    return await respond(request.app.state.paper.configure(body.model_dump()))


@router.post('/refresh',dependencies=[Depends(mutation)])
async def refresh(request:Request):
    return await respond(request.app.state.paper.refresh())


@router.get('/export',dependencies=[Depends(owner)])
async def export(request:Request):
    import asyncio
    try:
        data = await asyncio.to_thread(request.app.state.paper.ready().store.backup)
        return Response(data,media_type='application/vnd.sqlite3',headers=dict(HEADERS,**{'Content-Disposition':'attachment; filename="aura-paper-backup.sqlite3"'}))
    except PaperError:
        return JSONResponse({'code':'STORAGE_UNAVAILABLE','message':MESSAGES['STORAGE_UNAVAILABLE']},status_code=503,headers=HEADERS)


class AutoConfiguration(StrictModel):
    enabled: bool
    symbol: Literal['BTCUSDT'] = 'BTCUSDT'
    timeframe: Literal['1m','5m','15m','1h'] = '15m'
    expected_source: StrictStr = Field(default='Binance · Spot',min_length=1,max_length=120)
    fallback_policy: Literal['SKIP','PAPER_SETTINGS'] = 'SKIP'

    model_config = ConfigDict(extra='forbid',strict=True)


@router.post('/auto',dependencies=[Depends(mutation)])
async def auto_configuration(request:Request,body:AutoConfiguration):
    return await respond(request.app.state.paper.configure_auto(body.model_dump()))

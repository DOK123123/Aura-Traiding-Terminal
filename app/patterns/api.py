import asyncio
import time
import sqlite3
import logging
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..gold import FAILURES, failure_reason
from ..models import INTERVALS, data_fresh
from .config import PatternConfig
from .history import history_service
from .engine import evaluate
from .backtesting import replay
from .outcomes import outcome

router=APIRouter(prefix='/api/patterns',tags=['Historical Pattern Engine'])
compute_slots=asyncio.Semaphore(2)
logger = logging.getLogger(__name__)


class PatternRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    symbol: Literal['XAUUSD','BTCUSDT']='XAUUSD'
    timeframe: Literal['1m','5m','15m','1h']='15m'
    context: Literal[500,2000]=500
    config: PatternConfig=Field(default_factory=PatternConfig)
    as_of: int | None=Field(None,gt=0)
    chart_source: Literal['Binance · Spot', 'Dukascopy · XAUUSD BID', 'TradingView · OANDA:XAUUSD'] | None = None


class BacktestRequest(PatternRequest):
    start_at: int | None=Field(None,gt=0)
    end_at: int | None=Field(None,gt=0)
    max_points: int=Field(50,ge=1,le=100)

    @model_validator(mode='after')
    def dates(self):
        if self.start_at and self.end_at and self.start_at>self.end_at:
            raise ValueError('start_at must precede end_at')
        if self.as_of is not None:
            raise ValueError('Use analysis as_of for point replay; start_at/end_at for backtest')
        return self


@router.get('/config')
def defaults():
    return PatternConfig().model_dump()


def metadata(data,body):
    return dict(symbol=body.symbol,timeframe=body.timeframe,source=data.source,
                archive_bars=len(data.candles),archive_first=data.candles[0].time,
                archive_last=data.candles[-1].time,fetched_at=data.fetched_at,
                history_requested=data.requested,data_note=data.note)


def failure(exc,status=503):
    logger.warning('Pattern request failed: %s', exc)
    return JSONResponse(status_code=status,content=dict(status='NO DATA',signal=None,confidence=None,
                         message=str(exc) if isinstance(exc,ValueError) else failure_reason(exc)))


@router.post('/analyze')
async def analyze_patterns(body: PatternRequest,request: Request):
    try:
        data=await history_service.get(request.app.state.client,body.symbol,body.timeframe)
        step=INTERVALS[body.timeframe]; target=len(data.candles)-1
        if body.as_of is not None:
            if body.as_of>data.candles[-1].time+step:
                raise ValueError('Точка позже последней доступной закрытой свечи.')
            target=max((i for i,c in enumerate(data.candles) if c.time+step<=body.as_of),default=-1)
        async with compute_slots:
            result=await asyncio.to_thread(evaluate,data.candles,step,body.context,body.config,target)
        result.update(metadata(data,body))
        result['mode']='POINT REPLAY' if body.as_of is not None else 'CURRENT MARKET'
        if body.as_of is not None:
            # Evaluation results are attached AFTER prediction; never passed to similarity.
            result['actual_after_point']={str(h):outcome(data.candles,target,h) for h in body.config.horizons}
        elif not data_fresh(data.candles[-1], body.timeframe, time.time()):
            result['status']='DELAYED'; result['signal']='WAIT'
            result['explanation']['risks'].append('Последнее закрытие задержано / рынок закрыт. Текущий направленный сигнал отключён.')
        if body.as_of is None:
            result['source_verified'] = body.chart_source == data.source
            if not result['source_verified']:
                result['status'] = 'SOURCE MISMATCH'
                result['signal'] = 'WAIT'
                result['explanation']['risks'].append('Источник графика не подтверждён или отличается от архива. Направленный сигнал отключён.')
        return result
    except ValueError as exc:
        return failure(exc,422)
    except FAILURES + (sqlite3.Error,) as exc:
        return failure(exc)


@router.post('/backtest')
async def backtest_patterns(body: BacktestRequest,request: Request):
    try:
        data=await history_service.get(request.app.state.client,body.symbol,body.timeframe)
        async with compute_slots:
            result=await asyncio.to_thread(replay,data.candles,INTERVALS[body.timeframe],body.context,
                                           body.config,body.start_at,body.end_at,body.max_points)
        return {**result,**metadata(data,body)}
    except ValueError as exc:
        return failure(exc,422)
    except FAILURES + (sqlite3.Error,) as exc:
        return failure(exc)

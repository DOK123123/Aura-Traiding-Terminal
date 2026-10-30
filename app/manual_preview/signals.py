"""Public-market observer inside the existing owner-protected Aura 5 preview."""
import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import time

from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import JSONResponse
from typing import Literal

from app.hunter.main import Hunter
from app.hunter.market import PublicMarket
from app.hunter.store import Store

ROOT=Path(__file__).resolve().parents[2]
router=APIRouter(prefix='/api/preview/signals')
log=logging.getLogger('aura.preview.signals')


async def run_observer(observer):
    try:
        async with asyncio.timeout(45):await observer.cycle()
        state=await asyncio.to_thread(observer.store.snapshot,time.time(),observer.quotes,observer.error)
        log.warning('PREVIEW_SIGNALS_PROBE frames=%s cycles=%d state=%s records=%d',
                    ','.join(state['fresh_frames']) or 'NONE',observer.cycles,state['state'],len(state['records']))
    except Exception:
        log.warning('PREVIEW_SIGNALS_PROBE_FAILED')
    await observer.run()


@asynccontextmanager
async def observer_lifespan(app, client, enabled: bool):
    app.state.preview_signals=None
    app.state.preview_signals_task=None
    market=None
    if enabled:
        try:
            # This is a separate public-observation journal, never the wallet.
            store=Store(ROOT/'work/manual-preview-signals.sqlite')
            market=PublicMarket(client)
            observer=Hunter(store,market,{'approved':[]})
            app.state.preview_signals=observer
            app.state.preview_signals_task=asyncio.create_task(run_observer(observer))
        except Exception:
            log.warning('PREVIEW_SIGNALS_STARTUP_FAILED')
    try:yield
    finally:
        task=app.state.preview_signals_task
        if task:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
        if market:await market.close()


@router.get('/snapshot')
async def snapshot(request:Request):
    h=request.app.state.preview_signals;task=request.app.state.preview_signals_task
    if h is None:
        return JSONResponse({'code':'PREVIEW_SIGNALS_UNAVAILABLE','exchange_execution':False},503)
    running=task is not None and not task.done()
    status={'running':running,'cycles':h.cycles,'last_cycle_at':h.last_cycle_at,'frame_errors':dict(h.frame_errors),
            'diagnostic_write_failures':h.diagnostic_write_failures}
    data=await asyncio.to_thread(h.store.snapshot,time.time(),dict(h.quotes),h.error if running else 'OBSERVER_STOPPED')
    data['observer']=status
    data['storage']='EPHEMERAL_RENDER_LOCAL'
    return data


@router.get('/inputs')
async def inputs(request:Request,frame:str=Query(pattern='^(5m|15m|1h|4h)$'),after:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100)):
    h=request.app.state.preview_signals
    if h is None:return JSONResponse({'code':'PREVIEW_SIGNALS_UNAVAILABLE'},503)
    return await asyncio.to_thread(h.store.export_inputs,frame,after,limit)


@router.get('/diagnostics')
async def diagnostics(request:Request,hours:int=Query(24,ge=24,le=48)):
    if hours not in (24,48):raise HTTPException(422,'INVALID_DIAGNOSTIC_WINDOW')
    h=request.app.state.preview_signals
    if h is None:return JSONResponse({'code':'PREVIEW_SIGNALS_UNAVAILABLE'},503)
    return await asyncio.to_thread(h.store.diagnostics,time.time(),hours)


@router.get('/journal')
async def journal(request:Request,hours:int=Query(24,ge=24,le=48),kind:Literal['decisions','samples']='decisions',
                  after:int=Query(0,ge=0),limit:int=Query(500,ge=1,le=1000)):
    if hours not in (24,48):raise HTTPException(422,'INVALID_DIAGNOSTIC_WINDOW')
    h=request.app.state.preview_signals
    if h is None:return JSONResponse({'code':'PREVIEW_SIGNALS_UNAVAILABLE'},503)
    return await asyncio.to_thread(h.store.export_diagnostics,time.time(),hours,kind,after,limit)

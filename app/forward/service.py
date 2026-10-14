"""Externally triggered forward capture, immutable outcomes, no trading dependencies."""
import asyncio
from copy import deepcopy
import os
from pathlib import Path
import time
import sqlite3
import logging
from app.lab.models import digest
from app.intelligence.market_context import SOURCE
from .models import (ForwardError,STEPS,HORIZONS,record,verify,frame,realized,policy_hash,probabilities,VERSION,scheduler_secret_valid)
from .stats import summarize
from .storage import SQLiteStore,SupabaseStore


class Service:
    def __init__(self,market,store=None,clock=time.time,reason=None):
        self.market=market;self.store=store;self.clock=clock;self.reason=reason
        self.task=None;self.closed=False;self.policy_hash=policy_hash()
    @property
    def cohort(self):
        index=getattr(self.market,'analog_index',None)
        if index is None:return None
        return digest(dict(model=index.pack['version'],artifact=index.pack['content_sha256'],policy=self.policy_hash))
    def ready(self):
        if self.store is None:raise ForwardError(self.reason or 'STORAGE_NOT_CONFIGURED')
        if self.cohort is None:raise ForwardError('ARTIFACT_REQUIRED')
    async def close(self):
        self.closed=True
        if self.task and not self.task.done():
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        if self.store:await self.store.close()
    async def tick(self):
        self.ready()
        if self.closed:raise ForwardError('SERVICE_CLOSED')
        if self.task is None or self.task.done():self.task=asyncio.create_task(self._bounded_tick())
        return await asyncio.shield(self.task)
    async def _bounded_tick(self):
        try:
            async with asyncio.timeout(55):return await self._tick()
        except TimeoutError:
            logging.getLogger(__name__).warning('Forward validation tick failed: code=CAPTURE_TIMEOUT')
            raise ForwardError('CAPTURE_TIMEOUT') from None
        except ForwardError as exc:
            logging.getLogger(__name__).warning('Forward validation tick failed: code=%s',exc.code)
            raise
    def baseline(self,row,horizon):
        index=self.market.analog_index;tf=row['timeframe'];at=row['timestamp'];step=STEPS[tf]
        pool=[r for r in index.frames[tf] if r['resolved_at']<at and r['timestamp']+250*step<at]
        samples=dict(unconditional=pool,same_regime=[r for r in pool if r['regime']==row['regime']],
            simple_trend=[r for r in pool if r['trend_direction']==row['trend_direction']])
        values={}
        for key,rs in samples.items():
            returns=[float(r['outcomes'][str(horizon)]['return_pct']) for r in rs]
            values[key]=dict(mean_return_pct=sum(returns)/len(returns) if returns else None,
                probabilities=[sum(x<0 for x in returns)/len(returns),sum(x==0 for x in returns)/len(returns),sum(x>0 for x in returns)/len(returns)] if returns else None,
                count=len(returns))
        values['no_change']=dict(mean_return_pct=0.0,probabilities=[0.0,1.0,0.0],count=None)
        return values
    def prediction(self,value,bars,created_ms):
        tf=value.get('timeframe');step=STEPS[tf];at=value.get('last_closed_at');now=created_ms/1000
        if (value.get('status')!='OK' or value.get('freshness',{}).get('status')!='FRESH' or
                type(at) is not int or at!=int(now)//step*step or not at<=now<at+step):raise ForwardError('STALE_OR_RETROACTIVE')
        if value.get('symbol')!='BTCUSDT' or value.get('source')!=SOURCE or (value.get('history') or {}).get('source_sha256')!=digest([b.data() for b in bars]):
            raise ForwardError('SOURCE_OR_SNAPSHOT_MISMATCH')
        row=value['state'];analogs=value['analog_availability'];index=self.market.analog_index
        if analogs.get('artifact_sha256')!=index.pack['content_sha256']:raise ForwardError('ARTIFACT_MISMATCH')
        if row.get('timestamp')!=at or row.get('timeframe')!=tf or row.get('symbol')!='BTCUSDT' or row.get('version')!=index.pack['feature_version'] or analogs.get('query_closed_at')!=at:
            raise ForwardError('STATE_TIMESTAMP_MISMATCH')
        if any(p['confirmation_time']>at for p in row.get('confirmed_pivots',[])) or any(x and x['closed_at']>at for k,x in row['mtf'].items() if k in ('h1','h4')):
            raise ForwardError('FUTURE_FEATURES')
        fs=frame(bars,tf,now);base=next((b for b in fs if b.time+step==at),None)
        if base is None:raise ForwardError('MISSING_CLOSED_CANDLE')
        cohort=self.cohort;identifier=digest([cohort,tf,at]);forecasts={};baselines={}
        forecast=analogs.get('status')=='DESCRIPTIVE_ONLY' and analogs.get('non_overlapping_samples',0)>=20
        for h in HORIZONS:
            x=analogs.get('horizons',{}).get(str(h),{})
            forecasts[str(h)]=dict(mean_return_pct=x.get('mean_return_pct'),probabilities=probabilities(x)) if forecast else None
            baselines[str(h)]=self.baseline(row,h)
            for name in ('unconditional','same_regime','simple_trend'):
                expected=analogs['baselines'][name][str(h)]
                actual=baselines[str(h)][name]
                if expected['count']!=actual['count'] or (expected['mean_return_pct'] is not None and abs(expected['mean_return_pct']-actual['mean_return_pct'])>1e-9):
                    raise ForwardError('BASELINE_MISMATCH')
        body=dict(id=identifier,cohort=cohort,created_at_ms=created_ms,exchange='Binance',market_type='SPOT',symbol='BTCUSDT',timeframe=tf,
            closed_at=at,closed_price=str(base.close),creation_lag_ms=created_ms-at*1000,regime=row['regime'],structure=deepcopy(row),
            indicators=dict(rsi=row['rsi'],adx=row['trend_strength'],atr=row['atr']),mtf=deepcopy(row['mtf']),
            analog_count=analogs['eligible_analogs'],non_overlapping_samples=analogs['non_overlapping_samples'],effective_independent_sample_size=None,
            model_version=index.pack['version'],artifact_hash=index.pack['content_sha256'],forward_policy_hash=self.policy_hash,feature_configuration_hash=digest(dict(features=index.pack['feature_version'],software=index.pack['software'],normalizers=index.pack['normalizers'],forward_policy=self.policy_hash)),
            predicted_distributions=deepcopy(analogs['horizons']),forecasts=forecasts,baselines=baselines,
            status='FORECAST' if forecast else 'ABSTAINED',abstention_reason=None if forecast else 'INSUFFICIENT_ANALOG_DATA',
            freshness=deepcopy(value['freshness']),source_fetched_at=value.get('fetched_at'),source=value['source'],market_data_window_sha256=value['history']['source_sha256'],closed_candle_sha256=digest(base.data()),execution_enabled=False)
        core={k:v for k,v in body.items() if k not in ('created_at_ms','creation_lag_ms','source_fetched_at','freshness','market_data_window_sha256')}
        body['fingerprint']=digest(core)
        return record('PRED',identifier,body,created_ms,cohort,tf,at)
    async def _tick(self):
        now_ms=int(self.clock()*1000);slot=now_ms//300000;run_id='tick:'+str(slot)
        existing=await self.store.read(mode='run',after=slot,limit=1)
        if existing:return dict(verify(existing[0]),replayed=True)
        await self.store.append([record('TICK',run_id,dict(slot=slot,started_at_ms=now_ms),now_ms)])
        snapshots=await asyncio.gather(*(self.market.snapshot(tf) for tf in STEPS))
        bars=list(self.market.bars);predictions=[];rejected={}
        for value in snapshots:
            try:predictions.append(self.prediction(value,bars,int(self.clock()*1000)))
            except (ForwardError,KeyError,TypeError,ValueError) as exc:
                rejected[value.get('timeframe','UNKNOWN')]=exc.code if isinstance(exc,ForwardError) else 'INVALID_MARKET_RESPONSE'
        capture=await self.store.append(predictions) if predictions else dict(inserted=0,duplicates=0,corrections=0)
        pending=await self.store.read(mode='pending',limit=50,now=int(self.clock()))
        outputs=[]
        # Do not evaluate from a failed/stale latest feed. Cached confirmed history
        # is retained by 3.2, but outcomes wait for a successful fresh refresh.
        fresh=any(v.get('freshness',{}).get('status')=='FRESH' and v.get('status')=='OK' for v in snapshots)
        if fresh:
            frames={tf:frame(bars,tf,int(self.clock())) for tf in STEPS}
            for old in pending:
                pred=verify(old)
                for h in HORIZONS:
                    value=realized(pred,bars,h,int(self.clock()*1000),frame_cache=frames)
                    if value is not None:
                        outputs.append(record('OUTCOME',pred['id']+':'+str(h),value,int(self.clock()*1000),
                            pred['cohort'],pred['timeframe'],pred['closed_at'],pred['id'],h))
        evaluated=0;corrections=0
        for start in range(0,len(outputs),100):
            result=await self.store.append(outputs[start:start+100]);evaluated+=result['inserted'];corrections+=result['corrections']
        complete=dict(status='COMPLETED' if predictions else 'DATA_UNAVAILABLE',run_id=run_id,capture=capture,evaluated_outcomes=evaluated,
            corrections=corrections,rejected=rejected,pending_batch_limit=50,completed_at_ms=int(self.clock()*1000),execution_enabled=False)
        await self.store.append([record('COMPLETE' if predictions else 'FAILURE',run_id+(':complete' if predictions else ':failure'),complete,int(self.clock()*1000))])
        return complete
    async def dashboard(self,cohort=None):
        if self.store is None:return dict(status=self.reason or 'STORAGE_NOT_CONFIGURED',backend=None,monitoring=None,
            statistics=None,journal=[],model_version=getattr(self.market,'analog_index',None).pack['version'] if getattr(self.market,'analog_index',None) else None,
            cohort=self.cohort,execution_enabled=False)
        selected=self.cohort if cohort is None else cohort
        if selected is None:
            monitor=await self.store.status();records=[]
        else:
            monitor,records=await asyncio.gather(self.store.status(selected),self.store.read(mode='recent',limit=100,cohort=selected))
        journal=[]
        outcomes={};corrected=set()
        for entry in records:
            body=verify(entry)
            if entry['kind']=='OUTCOME':outcomes.setdefault(entry['ref'],{})[str(entry['horizon'])]=body
            elif entry['kind']=='CORRECTION':corrected.add(body['prediction_id'])
        for row in records:
            body=verify(row)
            if row['kind']=='PRED':journal.append(dict(id=row['id'],created_at_ms=row['created_ms'],timeframe=row['tf'],regime=body['regime'],status=body['status'],forecasts=body['forecasts'],outcomes=outcomes.get(row['id'],{}),corrected=row['id'] in corrected))
        configured_scheduler=scheduler_secret_valid(os.getenv('AURA_FORWARD_SCHEDULER_SECRET',''),os.getenv('AURA_TESTNET_VIEW_PASSWORD',''),os.getenv('AURA_FORWARD_SUPABASE_SERVICE_KEY',''))
        now_ms=int(self.clock()*1000);last_tick=monitor['last'].get('TICK');last_capture=monitor['last'].get('PRED');last_complete=monitor['last'].get('COMPLETE')
        collection='SCHEDULER_NOT_CONFIGURED' if not configured_scheduler else 'NO_SCHEDULE_OBSERVED' if not last_tick else 'LAST_RUN_INCOMPLETE' if (not last_complete or last_tick>last_complete) and now_ms-last_tick>120000 else 'NO_FRESH_CAPTURES' if not last_capture or now_ms-last_capture>900000 else 'RECENT_CAPTURE_OBSERVED'
        selected_model=verify(next(r for r in records if r['kind']=='PRED'))['model_version'] if any(r['kind']=='PRED' for r in records) else None
        return dict(collection_state=collection,status='CONFIGURED' if self.cohort else 'ARTIFACT_REQUIRED',backend=self.store.backend,
            server_now_ms=int(self.clock()*1000),monitoring=monitor,statistics=summarize(records,partial=True),journal=journal[-30:],cohort=selected,current_cohort=self.cohort,
            model_version=selected_model or (self.market.analog_index.pack['version'] if self.cohort else None),
            scheduler_configured=configured_scheduler,execution_enabled=False)


def configured(market):
    local=os.getenv('AURA_FORWARD_SQLITE_PATH','');url=os.getenv('AURA_FORWARD_SUPABASE_URL','');key=os.getenv('AURA_FORWARD_SUPABASE_SERVICE_KEY','')
    try:
        if local and (url or key):raise ForwardError('AMBIGUOUS_STORAGE_CONFIGURATION')
        if local:
            if os.getenv('RENDER','').lower() in ('true','1'):raise ForwardError('RENDER_REQUIRES_DURABLE_STORAGE')
            store=SQLiteStore(Path(local))
        elif url or key:store=SupabaseStore(url,key)
        else:store=None
        return Service(market,store)
    except ForwardError as exc:return Service(market,None,reason=exc.code)
    except (sqlite3.Error,OSError,ValueError):return Service(market,None,reason='STORAGE_CONFIGURATION_UNAVAILABLE')

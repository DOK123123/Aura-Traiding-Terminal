"""Causal hypotheses adapted to the existing Lab v2 execution contract."""
from bisect import bisect_right
from decimal import Decimal as D
import json
from pathlib import Path
from app.lab.models import SOURCE,precise
from app.lab.v2_strategies import prepare,decide,wait
from scripts.research_candidates import registry as existing_registry

ROOT=Path(__file__).resolve().parents[2]

class HypothesisDecisions:
    def __init__(self,bars):
        self.data=prepare(bars,900);self.hour=prepare(bars,3600)
        self.context4h=prepare(bars,14400)
        self.hour_closed=[b.time+3600 for b in self.hour['bars']]
        protocol=json.loads((ROOT/'docs/RESEARCH_CYCLE_PROTOCOL.json').read_text())
        self.reversion=existing_registry(protocol)['C'].generate(bars)

    @precise
    def decision(self,index:int,name:str,scale:str='1') -> dict:
        data=self.data;bars=data['bars'];b=bars[index];closed_at=b.time+900
        if index<249:return wait('WARMUP')
        av=data['atr'][index];ax=data['adx'][index]
        if av is None or av<=0 or ax is None:return wait('INDICATORS_UNAVAILABLE')
        regime='RANGE' if ax<=20 else 'TREND' if ax>=25 else 'TRANSITION'
        if name=='REGIME_SWITCHING':
            h=bisect_right(self.hour_closed,closed_at)-1
            if h<249 or self.hour['adx'][h] is None:return wait('CLOSED_1H_WARMUP_UNAVAILABLE')
            hx=self.hour['adx'][h]
            regime='RANGE' if hx<=20 else 'TREND' if hx>=25 else 'TRANSITION'
            if regime=='TRANSITION':return dict(wait('REGIME_TRANSITION'),regime=regime,context_closed_at=self.hour_closed[h])
            chosen='MEAN_REVERSION' if regime=='RANGE' else 'TREND_ATR'
        else:chosen=name
        if chosen in ('VOLATILITY_BREAKOUT','TREND_ATR'):
            plan=decide(data,index,'DONCHIAN' if chosen=='VOLATILITY_BREAKOUT' else 'TREND_ATR',closed_at=closed_at)
        elif chosen=='MEAN_REVERSION':
            d=self.reversion[index]
            plan=self.plan(d.direction,b.close,d.stop_distance,d.target_distance,closed_at) if d.direction else wait('MEAN_REVERSION_FILTERS_REJECTED')
        elif chosen=='LIQUIDITY_SWEEP':
            prior=bars[index-20:index];lo=min(x.low for x in prior);hi=max(x.high for x in prior)
            volume=sum((x.volume for x in prior),D(0))/20;atr=D(str(av))
            long=b.low<lo-atr*D('.1') and b.close>lo and b.close>b.open
            short=b.high>hi+atr*D('.1') and b.close<hi and b.close<b.open
            gates=dict(reclaim_long=long,reclaim_short=short,volume=volume>0 and b.volume>=volume*D('1.2'),weak_trend=ax<25)
            direction='LONG' if long else 'SHORT' if short else None
            plan=self.plan(direction,b.close,atr*2,atr*4,closed_at) if direction and gates['volume'] and gates['weak_trend'] else wait('SWEEP_PROXY_FILTERS_REJECTED',gates)
        else:raise ValueError('UNKNOWN_HYPOTHESIS')
        plan=dict(plan,regime=regime)
        if name=='REGIME_SWITCHING':plan['context_closed_at']=self.hour_closed[h]
        if plan.get('direction'):
            sign=1 if plan['direction']=='LONG' else -1;s=D(scale)
            plan.update(stop_loss=str(b.close-(b.close-D(plan['stop_loss']))*s),take_profit=str(b.close+(D(plan['take_profit'])-b.close)*s),reason='AI_LAB:'+name,source=SOURCE)
            if sign*(b.close-D(plan['stop_loss']))<=0:raise ValueError('INVALID_PLAN')
        return plan

    @staticmethod
    def plan(direction,close,stop,target,at):
        sign=1 if direction=='LONG' else -1
        return dict(direction=direction,signal_at=at,original_signal_at=at,strategy_timeframe='15m',reason='AI_LAB_SETUP',source=SOURCE,stop_loss=str(close-sign*stop),take_profit=str(close+sign*target))

    def rows(self,name,start,end,scale='1'):
        for i,b in enumerate(self.data['bars']):
            at=b.time+900
            if start<at<=end:yield dict(closed_at=at,decision=self.decision(i,name,scale))

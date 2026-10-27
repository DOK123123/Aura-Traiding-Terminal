"""Replay the unchanged analyst against availability-filtered closed prefixes."""
from bisect import bisect_right
from dataclasses import dataclass
from decimal import Decimal as D
import re
import time
from app.models import Candle
from app.aura_trader5_scenarios import assess
from .config import Config, digest
from .dataset import Dataset, STEPS, SOURCE


@dataclass(frozen=True)
class Signal:
    id: str
    candle_close: int
    available_at: int
    valid_until: int
    side: str
    low: D
    high: D
    stop: D
    target: D

    def validate(self):
        if self.side not in ('LONG','SHORT') or not isinstance(self.id,str) or not re.fullmatch(r'[0-9a-f]{64}',self.id):
            raise ValueError('INVALID_SIGNAL')
        if any(type(v) is not int for v in (self.candle_close,self.available_at,self.valid_until)) or not 0<self.candle_close<=self.available_at<self.valid_until or self.available_at-self.candle_close>=300 or self.valid_until>self.available_at+60:
            raise ValueError('INVALID_SIGNAL_AVAILABILITY')
        if any(not isinstance(v,D) or not v.is_finite() or v<=0 for v in (self.low,self.high,self.stop,self.target)) or self.low>self.high:
            raise ValueError('INVALID_SIGNAL_LEVELS')
        if not (self.stop<self.low<=self.high<self.target if self.side=='LONG' else self.target<self.low<=self.high<self.stop):
            raise ValueError('INVALID_SIGNAL_GEOMETRY')


def build(dataset: Dataset, config: Config, start: int, end: int, deadline: float):
    config.validate()
    availability={tf:[b.available_at for b in bars] for tf,bars in dataset.frames.items()}
    candles={tf:[Candle(b.time,*[float(getattr(b,k)) for k in ('open','high','low','close','volume')]) for b in bars] for tf,bars in dataset.frames.items()}
    signals=[];decisions=[]
    for b in dataset.frames['5m']:
        now=b.available_at
        if not start<=now<end:continue
        if time.monotonic()>deadline:raise ValueError('COMPUTE_TIMEOUT')
        windows={}
        for tf in STEPS:
            stop=bisect_right(availability[tf],now)
            windows[tf]=candles[tf][max(0,stop-config.window_bars):stop]
        if any(len(v)<config.window_bars for v in windows.values()):
            decisions.append(dict(time=now,candle_close=b.time+300,state='WAIT',reason='WARMUP_200_PER_FRAME'));continue
        try:result=assess(windows,now,float(config.tick))
        except ValueError:
            decisions.append(dict(time=now,candle_close=b.time+300,state='WAIT',reason='CLOSED_CONTEXT_UNAVAILABLE'));continue
        identifier=digest(dict(source=SOURCE,strategy=config.strategy,price_tick=config.tick,closed_at=b.time+300))
        decisions.append(dict(id=identifier,time=now,candle_close=b.time+300,state=result['state'],reason='|'.join(result['reasons'])))
        if result['state'] in ('LONG','SHORT'):
            p=result['scenario'];zone=p['entry_zone']
            signal=Signal(identifier,b.time+300,now,result['valid_until'],result['state'],
                          D(str(zone['low'])),D(str(zone['high'])),D(str(p['stop_loss'])),D(str(p['take_profit'])))
            signal.validate();signals.append(signal)
    return signals,decisions

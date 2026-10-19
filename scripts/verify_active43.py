"""Synthetic TEST ONLY fixtures; no source/API injection into the application.

Used solely by offline unit/PostgreSQL CLI verification. Production imports none
of this module. Natural historical tests use real closed-prefix analysis instead.
"""
from copy import deepcopy
from decimal import Decimal as D
from app.lab.models import Bar,digest
from app.automated.engine import DemoError
from app.active43.core import SOURCE
from app.active43.strategies import STEPS

class FixtureMarket:
    def __init__(self,side='LONG',timeframe='15m'):
        self.side=side;self.step=STEPS[timeframe];self.signal=True;self.failure=None
        start=1700000000//86400*86400-1000*self.step
        self.bars=[Bar(start+i*self.step,D(100),D(101),D(99),D(100),D(100)) for i in range(1000)]
    async def close(self):pass
    async def snapshot(self,cfg):
        if self.failure:raise DemoError(self.failure)
        at=self.bars[-1].time+self.step
        decision=dict(direction=self.side if self.signal else None,reason='TEST_ONLY_SYNTHETIC' if self.signal else 'NO_SIGNAL',
            source=SOURCE,source_sha256=digest([b.data() for b in self.bars]),signal_at=at,
            stop_loss='98' if self.side=='LONG' else '102',take_profit='104' if self.side=='LONG' else '96',
            exit_long=False,exit_short=False,atr='2')
        return self.bars,decision,at+30
    def add(self,open='100',high='101',low='99',close='100'):
        self.bars.append(Bar(self.bars[-1].time+self.step,*map(D,(open,high,low,close,'100'))))
        if len(self.bars)>1290:self.bars=self.bars[-1290:]

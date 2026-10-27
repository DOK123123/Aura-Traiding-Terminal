"""Isolated Manual Paper lifecycle. No Active43 imports or state access."""
import asyncio
import hashlib
import os
from pathlib import Path
import sqlite3
import time
from dataclasses import asdict
from decimal import Decimal

from .bitget import fetch_execution_quote
from .commands import ManualCommands
from .core import ManualPaper
from .quotes import QuoteRejected
from .store import ManualStore


class Service:
    def __init__(self, store=None, *, client=None, clock=time.time, durable=False, error=None):
        self.store=store
        self.client=client
        self.clock=clock
        self.durable=durable
        self.error=error
        self.lock=asyncio.Lock()
        self.last_check=None
        self.protection_error=None

    def ready(self):
        if self.error or self.store is None:
            raise ValueError(self.error or 'MANUAL_PAPER_DISABLED')
        return self.store

    async def db(self, fn, *args):
        try:
            return await asyncio.to_thread(fn,*args)
        except (sqlite3.Error,OSError):
            raise ValueError('STORAGE_UNAVAILABLE') from None
        except (KeyError,TypeError,ArithmeticError):
            raise ValueError('CORRUPT_JOURNAL') from None

    async def load(self):
        store=self.ready()
        ledger,version=await self.db(store.load)
        if ledger is None:
            # Concurrent first reads must converge on the same initial account.
            try:
                await self.db(store.save,ManualPaper(),0)
            except ValueError as exc:
                if str(exc)!='CONCURRENT_UPDATE':
                    raise
            ledger,version=await self.db(store.load)
        return ledger,version

    async def close(self):
        if self.store is not None and hasattr(self.store,'close'):
            await asyncio.to_thread(self.store.close)

    async def quote(self):
        self.ready()
        return await fetch_execution_quote(self.client,clock=self.clock)

    def fresh(self,q):
        if (q.get('source')!='Bitget USDT-M Futures' or q.get('symbol')!='BTCUSDT'
                or q.get('product')!='USDT-FUTURES'):
            raise QuoteRejected('SOURCE_MISMATCH')
        if type(q.get('time')) is not int or not 0<=self.clock()*1000-q['time']<=5000:
            raise QuoteRejected('STALE_QUOTE')

    def commands(self):
        commands=ManualCommands(self.ready())
        commands.validate_quote=self.fresh
        return commands

    async def preview(self, body, *, scenario_check=None):
        """Calculate on a detached ledger; no account/receipt is written."""
        async with self.lock:
            ledger, version = await self.db(self.ready().load)
            ledger = ledger or ManualPaper()
            q = await self.quote()
            self.fresh(q)
            if scenario_check is not None:
                await scenario_check(q)
            self.fresh(q)
            entry = q['ask'] if body['side'] == 'LONG' else q['bid']
            if Decimal(body['quantity']) > q['ask_size' if body['side']=='LONG' else 'bid_size']:
                raise ValueError('INSUFFICIENT_QUOTE_LIQUIDITY')
            limit = body.get('entry_limit')
            if limit is not None and (entry > Decimal(limit) if body['side']=='LONG' else entry < Decimal(limit)):
                raise ValueError('ENTRY_PRICE_MOVED')
            before = ledger.balance
            p = ledger.open(body['side'], entry, body['stop'], body['target'], body['quantity'])
            stop_fee = p.stop * p.quantity * ledger.fee_rate
            target_fee = p.target * p.quantity * ledger.fee_rate
            risk = abs(p.entry-p.stop)*p.quantity+p.entry_fee+stop_fee
            reward = abs(p.target-p.entry)*p.quantity-p.entry_fee-target_fee
            return dict(mode='MANUAL_PAPER',virtual_only=True,real_money_execution='DISABLED',
                        read_only=True,version=version,side=p.side,entry=str(p.entry),
                        quantity=str(p.quantity),stop=str(p.stop),target=str(p.target),
                        balance=str(before),notional=str(p.entry*p.quantity),
                        risk=str(risk),risk_pct=str(risk/before*100),max_risk=str(before*ledger.max_risk),
                        entry_fee=str(p.entry_fee),stop_exit_fee=str(stop_fee),target_exit_fee=str(target_fee),
                        net_reward=str(reward),net_rr=str(reward/risk),quote_time=q['time'],
                        expires_at=q['time']+30000,fee_rate=str(ledger.fee_rate),
                        funding='NOT_INCLUDED',slippage='OBSERVED_BID_ASK_NO_GUARANTEED_FILL')

    async def open(self, body, *, scenario_check=None):
        async with self.lock:
            extra=dict(entry_limit=body.get('entry_limit'),analyst_at=body.get('analyst_at'))
            args=ManualCommands.arguments(body['side'],body['quantity'],body['stop'],body['target'],**extra)
            cached=await self.db(self.ready().lookup,body['request_id'],'OPEN',args)
            if cached is not None:
                return cached
            q=await self.quote()
            self.fresh(q)
            deadline = await scenario_check(q) if scenario_check is not None else None
            price=q['ask'] if body['side']=='LONG' else q['bid']
            if Decimal(body['quantity'])>q['ask_size' if body['side']=='LONG' else 'bid_size']:
                raise ValueError('INSUFFICIENT_QUOTE_LIQUIDITY')
            commands = self.commands()
            if deadline is not None:
                def validate(q):
                    self.fresh(q)
                    if self.clock()*1000 >= deadline:
                        raise ValueError('STALE_ANALYST')
                commands.validate_quote = validate
            from functools import partial
            return await self.db(partial(commands.open,body['request_id'],body['side'],
                                 body['quantity'],body['stop'],body['target'],dict(q,price=price),
                                 **extra,expires_at_ms=deadline))

    async def close_position(self, position_id, request_id):
        async with self.lock:
            args=dict(position_id=position_id,reason='MANUAL')
            cached=await self.db(self.ready().lookup,request_id,'CLOSE',args)
            if cached is not None:
                return cached
            ledger,_=await self.load()
            if ledger.position is None or ledger.position.id!=position_id:
                raise ValueError('POSITION_NOT_FOUND')
            q=await self.quote()
            price=q['bid'] if ledger.position.side=='LONG' else q['ask']
            return await self.db(self.commands().close,request_id,dict(q,price=price),position_id)

    async def state(self, *, offset=0, limit=50):
        ledger,version=await self.load()
        p=ledger.position
        result=dict(mode='MANUAL_PAPER',virtual_only=True,real_money_execution='DISABLED',
                    balance=str(ledger.balance),starting_balance='10000',realized_pnl=str(ledger.realized),
                    position=asdict(p) if p else None,version=version,storage_durable=self.durable,
                    storage_backend=getattr(self.store,'backend','SQLITE'),
                    equity=None,unrealized_pnl=None,position_net_pnl=None,quote=None,market_error=None,
                    protection_checked_at=self.last_check,protection_error=self.protection_error,
                    limits=dict(max_notional='2000',max_risk_pct='0.5',max_positions=1,fee_rate='0.0006',drawdown_limit_pct='10'),
                    trades=list(reversed(ledger.trades))[offset:offset+limit],
                    history_total=len(ledger.trades),history_has_more=offset+limit<len(ledger.trades),server_now=self.clock())
        try:
            q=await self.quote()
            self.fresh(q)
            result['quote']=q
            gross=Decimal('0')
            exit_fee=Decimal('0')
            if p:
                price=q['bid'] if p.side=='LONG' else q['ask']
                gross=(price-p.entry)*p.quantity*(1 if p.side=='LONG' else -1)
                exit_fee=price*p.quantity*ledger.fee_rate
            result.update(equity=str(ledger.balance+gross-exit_fee),unrealized_pnl=str(gross),
                          position_net_pnl=str(gross-exit_fee-(p.entry_fee if p else 0)))
        except (QuoteRejected,ValueError) as exc:
            result['market_error']=str(exc)
        return result

    async def protect(self):
        """Only closes an existing virtual position; never opens one or seeds state."""
        if self.store is None or self.error:
            return
        async with self.lock:
            ledger,_=await self.db(self.store.load)
            if ledger is None or ledger.position is None:
                return
            p=ledger.position
            if not isinstance(p.id,str):
                raise ValueError("CORRUPT_JOURNAL")
            q=await self.quote()
            self.fresh(q)
            price=q['bid'] if p.side=='LONG' else q['ask']
            stop=price<=p.stop if p.side=='LONG' else price>=p.stop
            target=price>=p.target if p.side=='LONG' else price<=p.target
            if stop or target:
                reason='STOP_LOSS' if stop else 'TAKE_PROFIT'
                key=hashlib.sha256(('protect:'+p.id).encode()).hexdigest()[:32]
                # Use observed bid/ask for gaps, never invent a fill at the stop.
                await self.db(self.commands().close,key,dict(q,price=price),p.id,reason)
            self.last_check=self.clock()
            self.protection_error=None

    async def run_protection(self):
        while True:
            try:
                await self.protect()
            except (ValueError,QuoteRejected) as exc:
                self.protection_error=str(exc)
            await asyncio.sleep(5)


def configured(client):
    if os.getenv('AURA_MANUAL_PAPER_ENABLED','').lower()!='true':
        return Service(error='MANUAL_PAPER_DISABLED')
    try:
        mode=os.getenv('AURA_MANUAL_PAPER_STORAGE','')
        if mode=='supabase':
            from .supabase_store import SupabaseStore
            store=SupabaseStore(os.getenv('AURA_MANUAL_PAPER_SUPABASE_URL',''),
                                os.getenv('AURA_MANUAL_PAPER_SUPABASE_SERVICE_KEY',''))
            return Service(store,client=client,durable=True)
        raw=os.getenv('AURA_MANUAL_PAPER_DB','')
        path=Path(raw)
        if not raw or not path.is_absolute() or path.name!='manual-paper.sqlite3' or path.is_symlink():
            raise ValueError('MANUAL_STORAGE_PATH_INVALID')
        durable=False
        if mode=='persistent-disk':
            mount=Path(os.getenv('AURA_MANUAL_PAPER_MOUNT','/var/data'))
            if (not mount.is_absolute() or mount==Path('/') or not os.path.ismount(mount)
                    or mount.resolve()!=mount or not path.resolve().is_relative_to(mount)):
                raise ValueError('PERSISTENT_DISK_REQUIRED')
            durable=True
        elif mode!='development' or os.getenv('RENDER'):
            raise ValueError('PERSISTENT_DISK_REQUIRED')
        return Service(ManualStore(path,required_mount=mount if durable else None),client=client,durable=durable)
    except (ValueError,OSError):
        return Service(error='PERSISTENT_STORAGE_NOT_READY')

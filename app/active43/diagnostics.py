"""Bounded, owner/scheduler authenticated probes. No engine, control or DB writes."""
import asyncio
import os
import re
import time
from copy import deepcopy

from app.automated.engine import DemoError
from .core import IDENTITY, SOURCE, SCOPE
from .market import Market
from .bitget import MarketError
from .storage import Store
from .strategies import STEPS, VERSION


def configuration() -> dict:
    """Names and booleans only: never return environment values or key fragments."""
    from .service import scheduler_configured,scheduler_auth_configuration
    generic = os.getenv('AURA_ACTIVE43_ENABLED')
    bitget = os.getenv('AURA_ACTIVE43_BITGET_ENABLED', '').lower() == 'true'
    names = ('AURA_ACTIVE43_BITGET_SUPABASE_URL', 'AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY')
    return dict(server_enabled=bitget and (generic is None or generic.lower() == 'true'),
                bitget_enabled=bitget, explicit_global_stop=generic is not None and generic.lower() != 'true',
                missing_variables=[name for name in names if not os.getenv(name)],
                scheduler_secret_valid=scheduler_configured(),scheduler_auth=scheduler_auth_configuration())


class Diagnostics:
    """One probe per service, shared requests, 20-second cache and 25-second budget."""
    def __init__(self, service):
        self.service = service
        self.task = None
        self.cached = None
        self.cached_at = 0
        self.scheduler_probe_at = None

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def run(self, scheduler_delivery: bool = False) -> dict:
        # Delivery proves this authenticated HTTP request, NOT periodic execution.
        if scheduler_delivery:
            self.scheduler_probe_at = int(self.service.clock())
        if self.cached is not None and 0 <= time.monotonic() - self.cached_at < 20:
            value = deepcopy(self.cached)
        else:
            if self.task is None or self.task.done():
                self.task = asyncio.create_task(self.probe())
            value = deepcopy(await asyncio.shield(self.task))
        value['scheduler']['last_diagnostic_delivery_at'] = self.scheduler_probe_at
        value['scheduler']['diagnostic_delivery_confirmed'] = scheduler_delivery
        return value

    async def probe(self) -> dict:
        config = configuration()
        result = dict(scope=SCOPE, market_source=SOURCE, strategy_version=VERSION,
                      paper_only=True, exchange_execution=False, read_only=True, state_changed=False,
                      production_paper_verified=False, checked_at=int(self.service.clock()),
                      checked_on_render=os.getenv('RENDER', '').lower() in ('true', '1'),
                      render_commit=os.getenv('RENDER_GIT_COMMIT') if re.fullmatch('[a-f0-9]{40}', os.getenv('RENDER_GIT_COMMIT', '')) else None,
                      configuration=config, bitget=dict(status='ERROR', code='DIAGNOSTIC_TIMEOUT'),
                      supabase=dict(status='ERROR', code='DIAGNOSTIC_TIMEOUT'),
                      scheduler=dict(status='ERROR', code='NO_CONFIRMED_TICK' if config['scheduler_secret_valid'] else 'SCHEDULER_NOT_CONFIGURED', last_successful_tick=None),
                      virtual_balance=None, current_position=None, mode=None,
                      workflow_url='https://github.com/DOK123123/Aura-Traiding-Terminal/actions/workflows/aura-active43.yml')
        # Independent connections and budgets: a failed market probe cannot hide DB evidence.
        await asyncio.gather(self.market_probe(result), self.storage_probe(result))
        errors = [v['code'] for v in (result['bitget'], result['supabase'], result['scheduler']) if v['status'] != 'CONNECTED' and v['status'] != 'ACTIVE']
        if not config['server_enabled']:
            errors.insert(0, 'ACTIVE43_DISABLED' if config['explicit_global_stop'] else 'ACTIVE43_BITGET_DISABLED')
        result['errors'] = errors
        result['status'] = 'PASS' if not errors else 'BLOCKED'
        self.cached = deepcopy(result)
        self.cached_at = time.monotonic()
        return result

    async def market_probe(self, result: dict):
        market = Market(clock=self.service.clock)
        try:
            async with asyncio.timeout(24):
                quote = await market.client.quote()
                error = await market.specs()
                if error:
                    raise DemoError(error)
                candles = {}
                for tf in ('15m', '1h', '4h'):
                    step = STEPS[tf]
                    end = int(self.service.clock()) // step * step
                    rows = await market.client.candles(tf, end - 2 * step, end)
                    if rows['identity'] != IDENTITY or rows['bars'][-1]['time'] + step != end:
                        raise DemoError('STALE_OR_MISMATCHED_DATA')
                    candles[tf] = dict(last_closed_at=end, last_open_at=end-step, count=len(rows['bars']))
                # A slow probe must not label the starting quote as current.
                market.client.fresh_time(quote['server_at_ms'])
                if any(value['last_closed_at'] != int(self.service.clock()) // STEPS[tf] * STEPS[tf] for tf,value in candles.items()):
                    raise DemoError('STALE_OR_MISMATCHED_DATA')
                result['bitget'] = dict(status='CONNECTED', code=None, price=quote['last_price'],
                                        quote_at_ms=quote['server_at_ms'], identity=dict(IDENTITY), candles=candles,
                                        scope='CONNECTIVITY_AND_TWO_CLOSED_CANDLES_PER_TIMEFRAME_NOT_STRATEGY_VALIDATION')
        except (DemoError, MarketError) as exc:
            result['bitget'] = dict(status='ERROR', code=exc.code)
        except TimeoutError:
            result['bitget'] = dict(status='ERROR', code='DIAGNOSTIC_TIMEOUT')
        finally:
            await market.close()

    async def storage_probe(self, result: dict):
        store = None
        own = False
        try:
            async with asyncio.timeout(24):
                # Even if feature flags are OFF, credentials only authorize these
                # existing read paths. load() would seed an account and is forbidden.
                store = self.service.store
                if store is None:
                    url = os.getenv('AURA_ACTIVE43_BITGET_SUPABASE_URL', '')
                    key = os.getenv('AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY', '')
                    if not url or not key:
                        raise DemoError('ACTIVE43_STORAGE_NOT_CONFIGURED')
                    store = Store(url, key, self.service.config)
                    own = True
                await store.history(limit=1)
                result['supabase'] = dict(status='CONNECTED', code=None, history_rpc_verified=True,
                                           writes_tested=False, account_read_verified=False)
                env = await store.peek()
                result['supabase']['account_read_verified'] = True
                if env is None:
                    result['supabase']['account_status'] = 'NOT_INITIALIZED'
                    return
                state = env['state']
                if state['config'] != self.service.config:
                    raise DemoError('CONFIG_CHANGED')
                result.update(virtual_balance=state['balance'], mode=state['mode'],
                              current_position={k: state['position'][k] for k in ('id', 'direction', 'size', 'entry_price', 'stop_loss', 'active_stop', 'take_profit')} if state['position'] else None)
                last = state.get('last_successful_run_at')
                now = int(self.service.clock())
                active = type(last) is int and 0 <= now-last <= 360 and configuration()['scheduler_secret_valid']
                result['scheduler'].update(status='ACTIVE' if active else 'ERROR',
                    code=None if active else 'SCHEDULER_NOT_CONFIGURED' if not configuration()['scheduler_secret_valid'] else 'NO_CONFIRMED_TICK' if last is None else 'STALE_TICK',
                    last_successful_tick=last, last_tick=state['last_run_at'])
        except DemoError as exc:
            # A successful history call does not establish permission to read account.
            result['supabase'].update(status='ERROR', code=exc.code)
        except TimeoutError:
            result['supabase'].update(status='ERROR', code='DIAGNOSTIC_TIMEOUT')
        finally:
            if own and store is not None:
                await store.close()

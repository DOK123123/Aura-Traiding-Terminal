"""Auto42 freshness adapter; preserves the versioned analysis/analog module."""
import asyncio
from app.intelligence.market_context import MarketContext


async def snapshot_for_auto(market):
    if isinstance(market,MarketContext) and not market.closed:
        expected=int(market.clock())//900*900
        cached=(market.cache or {}).get('15m') or {}
        closed=cached.get('last_closed_at')
        # Only refresh a previously successful snapshot crossing a close boundary.
        # Failed refreshes retain the normal TTL/cooldown. One boundary override
        # per shared context, with its existing task reused by all consumers.
        if (cached.get('status')=='OK' and type(closed) is int and closed<expected
                and getattr(market,'auto_refresh_close',None)!=expected
                and (market.task is None or market.task.done())
                and market.monotonic()>=market.cooldown_until):
            market.auto_refresh_close=expected
            market.task=asyncio.create_task(market.refresh())
    return await market.snapshot('15m')

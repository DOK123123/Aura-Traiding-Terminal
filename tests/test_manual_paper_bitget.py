"""Server-side Bitget quote adapter tests. No external HTTP calls."""
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
import pytest
import asyncio
from functools import wraps

def offline_async(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return run

from app.manual_paper.bitget import fetch_verified_quote
from app.manual_paper.quotes import QuoteRejected

def candles(last_close=80100):
    end=1793007900 // 900 * 900
    return [SimpleNamespace(time=end-2700+i*900,
                            open=80000,high=80300,low=79900,
                            close=(last_close if i==2 else 80050),
                            volume=21) for i in range(3)]

@offline_async
async def test_double_fetch_verified():
    with patch("app.manual_paper.bitget.BitgetProvider") as cls:
        provider=cls.return_value
        provider.server_time=AsyncMock(return_value=1793007900000)
        provider.fetch=AsyncMock(side_effect=[candles(),candles()])
        quote=await fetch_verified_quote(object())
        assert quote["price"]==80100
        assert provider.fetch.await_count==2
        assert provider.server_time.await_count==2

@offline_async
async def test_changed_history_blocks_quote():
    with patch("app.manual_paper.bitget.BitgetProvider") as cls:
        provider=cls.return_value
        provider.server_time=AsyncMock(return_value=1793007900000)
        provider.fetch=AsyncMock(side_effect=[candles(),candles(80101)])
        with pytest.raises(QuoteRejected,match="HISTORY_CANDLE_CHANGED"):
            await fetch_verified_quote(object())

@offline_async
async def test_network_error_blocks_quote():
    from app.providers import DataUnavailable
    with patch("app.manual_paper.bitget.BitgetProvider") as cls:
        provider=cls.return_value
        provider.server_time=AsyncMock(return_value=1793007900000)
        provider.fetch=AsyncMock(side_effect=DataUnavailable("rate limited"))
        with pytest.raises(QuoteRejected,match="MARKET_UNAVAILABLE"):
            await fetch_verified_quote(object())

"""Server-owned adapter to Aura's unchanged causal Historical Pattern Engine."""
import asyncio
from decimal import Decimal
import math

from ..models import Candle,validate_candles,INTERVALS
from ..patterns.config import PatternConfig
from ..patterns.engine import evaluate
from .auto import Signal
from .models import PaperError


class SignalReader:
    def __init__(self, history, *, synchronize=False):
        self.history=history
        self.synchronize=synchronize
        self.slots=asyncio.Semaphore(1)

    async def read(self,window):
        try:
            async with asyncio.timeout(60):
                requirements={}
                if self.synchronize:
                    requirements=dict(required_candles=tuple(Candle(bar.time,
                        *(float(getattr(bar,k)) for k in ('open','high','low','close')),
                        None if bar.volume is None else float(bar.volume)) for bar in window.bars),
                        required_source=window.source)
                data=await self.history(window.symbol,window.timeframe,**requirements)
                if data.source!=window.source:
                    raise PaperError('SOURCE_MISMATCH')
                step=INTERVALS[window.timeframe]
                cutoff=(window.bars[-1].time+step)
                # Drop all later candles before feature generation, matching, MTF and outcomes.
                candles=[c for c in data.candles if c.time+step<=cutoff]
                validate_candles(candles,window.timeframe,now=cutoff,contiguous=True)
                tail=candles[-len(window.bars):]
                if len(tail)!=len(window.bars):
                    raise PaperError('SNAPSHOT_MISMATCH')
                for candle,bar in zip(tail,window.bars):
                    if candle.time!=bar.time or any(Decimal(str(getattr(candle,k)))!=getattr(bar,k) for k in ('open','high','low','close')):
                        raise PaperError('SNAPSHOT_MISMATCH')
                    if bar.volume is not None and (candle.volume is None or Decimal(str(candle.volume))!=bar.volume):
                        raise PaperError('SNAPSHOT_MISMATCH')
                async with self.slots:
                    result=await asyncio.to_thread(evaluate,candles,step,500,PatternConfig(),len(candles)-1,None,False)
                if result['status']!='OK' or result['as_of']!=cutoff:
                    raise PaperError('SIGNAL_ERROR')
                confidence=result.get('confidence')
                if type(confidence) not in (int,float) or not math.isfinite(confidence):
                    raise PaperError('SIGNAL_ERROR')
                signal=Signal(window.symbol,window.timeframe,window.source,window.bars[-1].time,
                              result['signal'],Decimal(str(confidence)))
                signal.validate(window)
                return signal
        except PaperError:raise
        except TimeoutError:raise PaperError('SIGNAL_UNAVAILABLE') from None
        except (KeyError,ValueError,TypeError):raise PaperError('SIGNAL_ERROR') from None
        except Exception:raise PaperError('SIGNAL_UNAVAILABLE') from None

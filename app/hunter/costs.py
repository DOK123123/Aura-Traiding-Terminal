"""One consistent 1 BTC cost convention. Levels are exit-side quote thresholds.

A supplied spread means entry is ALREADY the executable Ask (LONG)/Bid (SHORT).
Archive OHLC has no historical quotes: the fixed spread is a disclosed model.
Exit spread is represented by testing exit-side quotes against SL/TP, so it must
not be subtracted again from an already specified exit-side threshold.
"""
import json
import math
from numbers import Real
from pathlib import Path

RULES = json.loads(Path(__file__).with_name('rules.json').read_text())
COST_VERSION = 'AURA5_EXIT_QUOTE_COSTS_2'


def sign_for(direction: str) -> int:
    if direction not in ('LONG', 'SHORT'):
        raise ValueError('INVALID_DIRECTION')
    return 1 if direction == 'LONG' else -1


def entry_fill(reference: float, direction: str, *, multiplier: float = 1, quoted: bool = False) -> float:
    sign = sign_for(direction)
    half = 0 if quoted else RULES['costs']['full_spread_bps'] / 2e4 * multiplier
    slip = RULES['costs']['slippage_bps_per_side'] / 1e4 * multiplier
    return reference * (1 + sign * half) * (1 + sign * slip)


def exit_fill(quote: float, direction: str, *, multiplier: float = 1) -> float:
    return quote * (1 - sign_for(direction) * RULES['costs']['slippage_bps_per_side'] / 1e4 * multiplier)


def risk_reward(entry: float, stop: float, target: float, direction: str, step: int, hold: int,
                spread: float | None = None, *, multiplier: float = 1, entry_is_fill: bool = False) -> dict | None:
    if (direction not in ('LONG','SHORT') or type(step) is not int or step <= 0
            or type(hold) is not int or hold <= 0
            or any(not isinstance(x,Real) or isinstance(x,bool) or not math.isfinite(x) or x <= 0 for x in (entry,stop,target,multiplier))
            or spread is not None and (not isinstance(spread,Real) or isinstance(spread,bool) or not math.isfinite(spread) or spread < 0)):
        return None
    sign = sign_for(direction)
    e = entry if entry_is_fill else entry_fill(entry,direction,multiplier=multiplier,quoted=spread is not None)
    if sign*(e-stop) <= 0 or sign*(target-e) <= 0:
        return None
    s,t = exit_fill(stop,direction,multiplier=multiplier),exit_fill(target,direction,multiplier=multiplier)
    if any(not math.isfinite(x) or x <= 0 for x in (e,s,t)):
        return None
    fee = RULES['costs']['fee_bps_per_side']/1e4*multiplier
    funding = entry*math.ceil(hold*step/28800)*RULES['planning']['funding_reserve_bps_per_8h']/1e4*multiplier
    loss = sign*(e-s)+fee*(e+s)+funding
    reward = sign*(t-e)-fee*(e+t)-funding
    return {'entry_fill':e,'stop_fill':s,'target_fill':t,'stop_fees':fee*(e+s),'target_fees':fee*(e+t),
            'funding_reserve':funding,'net_loss':loss,'net_reward':reward,'net_rr':reward/loss,
            'cost_version':COST_VERSION,'entry_basis':'FILLED' if entry_is_fill else 'EXECUTABLE_QUOTE' if spread is not None else 'OHLC_SPREAD_PROXY'} if loss > 0 else None


def filled_in_zone(reference: float, zone: list, direction: str) -> bool:
    """The executable quote and the modeled fill must both respect the entry zone."""
    return zone[0] <= reference <= zone[1] and zone[0] <= entry_fill(reference,direction,quoted=True) <= zone[1]

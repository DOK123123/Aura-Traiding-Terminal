"""Causal, descriptive Aura 5 regimes; no probability or execution authority.

ADX14: conventional 20/25 weak/strong bands, with a deliberate transition gap.
The .1 ATR deadband reuses the explainable EMA rule; ER20=.3 reuses Hunter's
descriptive regime boundary. Fixed windows, no parameter search. These are
technical conventions tested on fixtures/archive, NOT statistically qualified.
"""
import math

import numpy as np

from app.hunter.engine import ema, wilder
from app.hunter.market import STEPS, validate_bars

VERSION = 'AURA5_REGIME_V1'
RULES = dict(adx_period=14, weak_adx=20, strong_adx=25, ema_deadband_atr=.1,
             efficiency_boundary=.3, range_window=20, slope_window=5, warmup=260)


def unknown(reason: str) -> dict:
    return dict(version=VERSION, state='UNKNOWN', reasons=[reason], metrics=None,
                rules=RULES.copy(), closed_only=True, statistical_status='UNVALIDATED')


def adx14(rows: list) -> np.ndarray:
    """Wilder directional movement; tied moves are both zero, flat ADX is zero."""
    x = np.asarray(rows, dtype=float)
    h, l, c = x[:, 2], x[:, 3], x[:, 4]
    up, down = np.diff(h), -np.diff(l)
    plus, minus = np.where((up > down) & (up > 0), up, 0), np.where((down > up) & (down > 0), down, 0)
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-c[:-1]), abs(l[1:]-c[:-1])))
    atr = wilder(tr)
    p = np.divide(100*wilder(plus), atr, out=np.zeros(len(tr)), where=atr > 0)
    m = np.divide(100*wilder(minus), atr, out=np.zeros(len(tr)), where=atr > 0)
    dx = np.divide(100*abs(p-m), p+m, out=np.zeros(len(tr)), where=p+m > 0)
    # DI's first valid observation is index 13, not the artificial zero prefix.
    return np.r_[np.full(14, np.nan), wilder(dx[13:])]


def classify(rows: list, frame: str, now: float) -> dict:
    if frame not in STEPS or type(now) not in (int, float) or not math.isfinite(now):
        return unknown('INVALID_FRAME_OR_CLOCK')
    step = STEPS[frame]
    try:
        validate_bars(rows, step)
    except (ValueError, TypeError):
        return unknown('INVALID_OHLCV_OR_GAP')
    if len(rows) < RULES['warmup'] or rows[-1][0]+step != int(now//step)*step:
        return unknown('INCOMPLETE_OR_STALE_CLOSED_HISTORY')
    b = rows[-RULES['warmup']:]
    x = np.asarray(b, dtype=float)
    h, l, c = x[:, 2], x[:, 3], x[:, 4]
    previous = np.r_[c[0], c[:-1]]
    atr = float(wilder(np.maximum(h-l, np.maximum(abs(h-previous), abs(l-previous))))[-1])
    adx = float(adx14(b)[-1])
    if not atr > 0 or not math.isfinite(adx):
        return unknown('INDICATOR_WARMUP_OR_ZERO_ATR')
    e20, e50 = ema(c, 20), ema(c, 50)
    slope = float((e20[-1]-e20[-6])/(5*atr))
    gap = float((e20[-1]-e50[-1])/atr)
    path = float(np.abs(np.diff(c[-21:])).sum())
    efficiency = float(abs(c[-1]-c[-21])/path) if path else 0.
    # Compare two non-overlapping CLOSED 10-bar high/low blocks, never a forming bar.
    old_high, old_low = float(max(h[-20:-10])), float(min(l[-20:-10]))
    high, low = float(max(h[-10:])), float(min(l[-10:]))
    structure = ('HH_HL' if high > old_high and low > old_low else
                 'LH_LL' if high < old_high and low < old_low else 'MIXED_OR_EQUAL')
    width = float(max(h[-20:])-min(l[-20:]))
    inside = bool(min(l[-21:-1]) <= c[-1] <= max(h[-21:-1]))
    strong = adx >= RULES['strong_adx'] and efficiency >= RULES['efficiency_boundary']
    deadband = RULES['ema_deadband_atr']
    if strong and gap > deadband and slope > deadband and structure == 'HH_HL':
        state, reasons = 'TREND_UP', ['STRONG_ADX', 'POSITIVE_EMA_GAP_AND_SLOPE', 'CLOSED_HH_HL', 'DIRECTIONAL_EFFICIENCY']
    elif strong and gap < -deadband and slope < -deadband and structure == 'LH_LL':
        state, reasons = 'TREND_DOWN', ['STRONG_ADX', 'NEGATIVE_EMA_GAP_AND_SLOPE', 'CLOSED_LH_LL', 'DIRECTIONAL_EFFICIENCY']
    elif (adx <= RULES['weak_adx'] and abs(slope) <= deadband
          and efficiency < RULES['efficiency_boundary'] and structure == 'MIXED_OR_EQUAL' and inside):
        state, reasons = 'RANGE', ['WEAK_ADX', 'FLAT_EMA_SLOPE', 'LOW_EFFICIENCY', 'NO_ORDERED_BLOCK_STRUCTURE', 'INSIDE_PRIOR_RANGE']
    else:
        state, reasons = 'TRANSITION', ['DIRECTION_STRENGTH_OR_STRUCTURE_NOT_ALIGNED']
    return dict(version=VERSION, state=state, reasons=reasons, closed_at=b[-1][0]+step,
                metrics=dict(adx14=adx, atr14=atr, ema20=float(e20[-1]), ema50=float(e50[-1]),
                             ema_gap_atr=gap, ema_slope_atr_per_bar=slope, efficiency20=efficiency,
                             structure=structure, range_high=float(max(h[-20:])), range_low=float(min(l[-20:])),
                             range_width_atr=width/atr, inside_prior_range=inside),
                rules=RULES.copy(), closed_only=True, statistical_status='UNVALIDATED')

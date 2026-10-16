"""Operational market-structure definitions. Recognition does not establish edge."""
from bisect import bisect_right
from decimal import Decimal as D
from statistics import median
import time
from app.intelligence.patterns import detect
from app.lab.indicators import ema, rsi, atr, adx
from app.lab.models import validate_series
from app.lab.series import higher, split_parts

VERSION = 'CONTEXT_VECTOR_1.1'
VECTOR_NAMES = ('trend', 'strength', 'volatility', 'volume', 'range_position',
    'support_distance', 'resistance_distance', 'liquidity', 'rsi', 'macd_atr',
    'pullback', 'high_leg', 'low_leg', 'structure_mask', 'structure_event',
    'fvg_side', 'order_block_side', 'range_detected', 'h1', 'h4', 'mtf_mask')


def zones(pivots, tolerance):
    """Bounded confirmed-pivot clustering; no outcome information."""
    groups=[];totals=[]
    for pivot in sorted(pivots[-32:], key=lambda p: p['price']):
        # Same ordered Decimal additions as sum(...), computed once per prefix
        # instead of re-summing a growing cluster for each new pivot.
        if groups and abs(pivot['price']-totals[-1]/len(groups[-1]))<=tolerance:
            groups[-1].append(pivot);totals[-1]+=pivot['price']
        else:
            groups.append([pivot]);totals.append(sum((pivot['price'],)))
    return [dict(price=total/len(g), touches=len(g),
        confirmed_at=max(p['confirmation_time'] for p in g)) for g,total in zip(groups,totals)]


def segment_states(bars, step=900, *, deadline=None):
    if not bars:return []
    validate_series(bars,step,bars[-1].time+step)
    c=[float(b.close) for b in bars];f=ema(c,20);s=ema(c,50)
    a=atr(bars);ax=adx(bars)[0];rs=rsi(c);m12=ema(c,12);m26=ema(c,26)
    highs=[];lows=[];active=None;ob=None;fvg=None;result=[]
    for i,b in enumerate(bars):
        if deadline is not None and time.monotonic()>deadline:raise TimeoutError("CONTEXT_COMPUTE_TIMEOUT")
        cutoff=b.time+step
        if i<249 or a[i] is None or a[i]<=0:
            if i>=4:
                for p in detect(bars[max(0,i-6):i+1],timeframe={900:'15m',3600:'1h',14400:'4h'}[step],cutoff=cutoff):
                    if p['pattern_id'] in ('swing_high','swing_low'):
                        upper=p['pattern_id']=='swing_high';pivot=bars[i-2];target=highs if upper else lows
                        target.append(dict(pivot_time=pivot.time,confirmation_time=cutoff,price=pivot.high if upper else pivot.low,kind='HIGH' if upper else 'LOW'))
                        del target[:-32]
            result.append(None);continue
        av=a[i];tol=D(str(av)) * D('.25');buffer=D(str(av)) * D('.1')
        prior_h=highs[-1]['price'] if highs else max(x.high for x in bars[i-20:i])
        prior_l=lows[-1]['price'] if lows else min(x.low for x in bars[i-20:i])
        def leg(points,positive,negative):
            if len(points)<2:return 'UNKNOWN'
            delta=points[-1]['price']-points[-2]['price']
            return 'EQUAL' if abs(delta)<=tol else positive if delta>0 else negative
        high_leg=leg(highs,'HH','LH');low_leg=leg(lows,'HL','LL')
        old_structure='UP' if high_leg=='HH' and low_leg=='HL' else 'DOWN' if high_leg=='LH' and low_leg=='LL' else 'UNKNOWN'
        direction=1 if f[i]>s[i] else -1 if f[i]<s[i] else 0
        breakout='LONG' if b.close>prior_h+buffer and bars[i-1].close<=prior_h else 'SHORT' if b.close<prior_l-buffer and bars[i-1].close>=prior_l else None
        failed=retest=None
        if active and 0<i-active['index']<=8:
            level=active['level'];long=active['side']=='LONG'
            if (b.close<level-buffer if long else b.close>level+buffer):
                failed='SHORT' if long else 'LONG';active=None
            elif not active['retested'] and (b.low<=level+tol and b.close>level+buffer and b.close>b.open if long else b.high>=level-tol and b.close<level-buffer and b.close<b.open):
                retest=active['side'];active['retested']=True
        if active and i-active['index']>8:active=None
        structure_event=None
        if breakout:
            confirmed_level=bool(highs) if breakout=='LONG' else bool(lows)
            against=(old_structure=='UP' and breakout=='SHORT') or (old_structure=='DOWN' and breakout=='LONG')
            structure_event=('CHoCH' if against else 'BOS') if confirmed_level else None
            active=dict(level=prior_h if breakout=='LONG' else prior_l, side=breakout,index=i,retested=False,confirmation_time=cutoff)
            opposing=[x for x in bars[max(0,i-8):i] if (x.close<x.open if breakout=='LONG' else x.close>x.open)]
            if opposing and confirmed_level:
                origin=opposing[-1];ob=dict(side=breakout,origin_time=origin.time,confirmation_time=cutoff,
                    lower=str(min(origin.open,origin.close)),upper=str(max(origin.open,origin.close)),expires_at=cutoff+16*step)
        if fvg and (cutoff>fvg['confirmation_time']+64*step or (b.low<=D(fvg['lower']) if fvg['side']=='LONG' else b.high>=D(fvg['upper']))):fvg=None
        if ob and (cutoff>ob['expires_at'] or (b.close<D(ob['lower']) if ob['side']=='LONG' else b.close>D(ob['upper']))):ob=None
        sweep_up=b.high>prior_h+buffer and b.close<prior_h
        sweep_down=b.low<prior_l-buffer and b.close>prior_l
        sweep='AMBIGUOUS' if sweep_up and sweep_down else 'SHORT' if sweep_up else 'LONG' if sweep_down else None
        # Exactly reuse the existing confirmed two-right-bar detector.
        detections=detect(bars[i-6:i+1],timeframe={900:'15m',3600:'1h',14400:'4h'}[step],cutoff=cutoff)
        new_pivots=[]
        for p in detections:
            if p['pattern_id'] in ('swing_high','swing_low'):
                upper=p['pattern_id']=='swing_high';pivot=bars[i-2]
                value=dict(pivot_time=pivot.time,confirmation_time=cutoff,price=pivot.high if upper else pivot.low,kind='HIGH' if upper else 'LOW')
                target=highs if upper else lows;target.append(value);del target[:-32];new_pivots.append(value)
            if p['pattern_id']=='fvg':
                up=p['direction']=='LONG';fvg=dict(side=p['direction'],confirmation_time=cutoff,
                    lower=str(bars[i-2].high if up else b.high),upper=str(b.low if up else bars[i-2].low))
        low50=min(x.low for x in bars[i-50:i]);high50=max(x.high for x in bars[i-50:i]);width=float(high50-low50)
        support_z=zones(lows,tol);resistance_z=zones(highs,tol)
        supp=[z for z in support_z if z['price']<=b.close];res=[z for z in resistance_z if z['price']>=b.close]
        support=max((z['price'] for z in supp),default=low50);resistance=min((z['price'] for z in res),default=high50)
        relative_volume=float(b.volume)/(sum(float(x.volume) for x in bars[i-20:i])/20) if sum(x.volume for x in bars[i-20:i])>0 else None
        history=[a[j]/c[j] for j in range(i-64,i) if a[j] is not None and a[j]>0]
        vol_ratio=(av/c[i])/median(history) if history else 1
        range_position=float(b.close-low50)/width if width>0 else .5
        is_range=ax[i]<=20 and width<=6*av
        regime='TREND_UP' if ax[i]>=25 and direction==1 else 'TREND_DOWN' if ax[i]>=25 and direction==-1 else 'RANGE' if is_range else 'UNKNOWN'
        depth=max(0,float(max(x.high for x in bars[i-20:i])-b.close)/av) if direction==1 else max(0,float(b.close-min(x.low for x in bars[i-20:i]))/av) if direction==-1 else 0
        sd=float(b.close-support)/av;rd=float(resistance-b.close)/av
        new_high_leg=leg(highs,'HH','LH');new_low_leg=leg(lows,'HL','LL')
        structure_mask=(1 if new_high_leg!='UNKNOWN' else 0)+(2 if new_low_leg!='UNKNOWN' else 0)
        structure_code=(1 if breakout=='LONG' else -1)*(2 if structure_event=='CHoCH' else 1) if structure_event else 0
        vector=[direction,ax[i]/100,av/c[i]*100,min(relative_volume or 0,5)/5,
            max(-2,min(3,range_position)),max(-10,min(10,sd)),max(-10,min(10,rd)),
            1 if sweep=='LONG' else -1 if sweep=='SHORT' else 0,rs[i]/100,(m12[i]-m26[i])/av,min(depth,10),
            1 if new_high_leg=='HH' else -1 if new_high_leg=='LH' else 0,
            1 if new_low_leg=='HL' else -1 if new_low_leg=='LL' else 0,structure_mask,structure_code,
            1 if fvg and fvg['side']=='LONG' else -1 if fvg else 0,
            1 if ob and ob['side']=='LONG' else -1 if ob else 0,int(is_range),0,0,0]
        result.append(dict(version=VERSION,timestamp=cutoff,pivot_timestamp=None,symbol='BTCUSDT',timeframe={900:'15m',3600:'1h',14400:'4h'}[step],
            segment_start=bars[0].time,vector=vector,trend_direction=direction,trend_strength=ax[i],regime=regime,
            trend_indicators=dict(ema20=f[i],ema50=s[i],adx14=ax[i],atr14=av,rsi14=rs[i],sample_count=i+1),
            high_leg=new_high_leg,low_leg=new_low_leg,structure_known_mask=structure_mask,confirmed_pivots=[dict(p,price=str(p['price'])) for p in new_pivots],
            support=str(support),resistance=str(resistance),support_source='CONFIRMED_PIVOT' if supp else 'ROLLING50_FALLBACK',resistance_source='CONFIRMED_PIVOT' if res else 'ROLLING50_FALLBACK',
            support_zones=[dict(max(supp,key=lambda z:z['price']),price=str(support))] if supp else [],resistance_zones=[dict(min(res,key=lambda z:z['price']),price=str(resistance))] if res else [],support_zone_count=len(support_z),resistance_zone_count=len(resistance_z),
            breakout=breakout,failed_breakout=failed,retest=retest,breakout_level=str(active['level']) if active else None,
            structure_event=structure_event,liquidity_sweep=sweep,equal_highs=leg(highs,'HH','LH')=='EQUAL',equal_lows=leg(lows,'HL','LL')=='EQUAL',
            fvg=fvg,order_block=ob,atr=av,volatility_ratio=vol_ratio,volatility='EXPANSION' if vol_ratio>=1.5 else 'COMPRESSION' if vol_ratio<=.65 else 'NORMAL',
            relative_volume=relative_volume,volume_confirmed=relative_volume is not None and relative_volume>=1.5,
            range_position=range_position,range_detected=is_range,pullback_depth_atr=depth,rsi=rs[i],macd_atr=(m12[i]-m26[i])/av,
            mtf=dict(h1=None,h4=None,known_mask=0,alignment=False),limitations=['Experimental operational SMC definitions; no claim about institutional orders.']))
    return result


def prepare(bars):
    """Every timeframe resets after missing full UTC blocks; never use old-gap MTF."""
    frame_maps={}
    for step in (3600,14400):
        frame=higher(bars,step);mapping={}
        for part in split_parts(frame,step):
            for state in segment_states(part,step):
                if state:mapping[state['timestamp']]=state
        frame_maps[step]=(sorted(mapping),mapping)
    output=[]
    for part in split_parts(bars,900):
        rows=segment_states(part)
        for row in rows:
            if row is None:continue
            values=[];mask=0
            for j,step in enumerate((3600,14400)):
                times,mapping=frame_maps[step];k=bisect_right(times,row['timestamp'])-1
                value=mapping[times[k]] if k>=0 else None
                if value and value['segment_start']>=part[0].time//step*step and row['timestamp']-value['timestamp']<step:
                    side=value['trend_direction'];mask|=1<<j
                    row['mtf']['h1' if j==0 else 'h4']=dict(direction=side,closed_at=value['timestamp'])
                else:side=0
                values.append(side)
            row['vector'][-3:]=values+[mask];row['mtf']['known_mask']=mask
            row['mtf']['alignment']=mask==3 and values[0]==values[1]==row['trend_direction']!=0
        output.append((part,rows))
    return output

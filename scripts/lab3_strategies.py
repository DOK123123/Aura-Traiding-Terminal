"""Fixed causal Lab3 candidates. No live/account dependencies or parameter search."""
from decimal import Decimal as D
from statistics import median,pstdev
import time
from app.lab.indicators import ema,rsi,atr,adx
from app.lab.models import Bar,precise
from app.lab.strategies import Decision


from app.lab.series import higher


def higher_alignment(bars,step):
    h=higher(bars,step);f=ema([float(b.close) for b in h],20);s=ema([float(b.close) for b in h],50)
    result=[];j=-1
    for b in bars:
        while j+1<len(h) and h[j+1].time+step<=b.time+900:j+=1
        result.append(None if j<0 or s[j] is None else 1 if f[j]>s[j] else -1 if f[j]<s[j] else 0)
    return result


@precise
def generate(bars,name,deadline=None):
    if name not in 'ABCDE' or len(name)!=1:raise ValueError('Unknown Lab3 strategy')
    c=[float(b.close) for b in bars];f=ema(c,20);m=ema(c,50);s=ema(c,200)
    a=atr(bars,14);rs=rsi(c,14);ax=adx(bars,14)[0]
    h1=higher_alignment(bars,3600) if name=='E' else [];h4=higher_alignment(bars,14400) if name=='E' else []
    width=[None if i<19 else 4*pstdev(c[i-19:i+1])/(sum(c[i-19:i+1])/20) for i in range(len(bars))] if name=='C' else []
    result=[];last=-10000;previous_long=previous_short=False;compressed=-10000
    for i,b in enumerate(bars):
        if deadline is not None and time.monotonic()>deadline:raise ValueError('COMPUTE_TIMEOUT')
        if i<200 or a[i] is None or a[i]<=0:
            result.append(Decision(reason='WARMUP'));continue
        long=short=xl=xs=False
        if name=='A':
            long=b.close>max(x.high for x in bars[i-55:i]);short=b.close<min(x.low for x in bars[i-55:i])
            xl=b.close<min(x.low for x in bars[i-20:i]);xs=b.close>max(x.high for x in bars[i-20:i])
        elif name=='B':
            el=m[i]>s[i] and c[i]>m[i] and ax[i]>=25;es=m[i]<s[i] and c[i]<m[i] and ax[i]>=25
            long=el and not previous_long and i-last>=64;short=es and not previous_short and i-last>=64
            previous_long,previous_short=el,es
            xl=m[i]<=s[i] or c[i]<m[i] or ax[i]<20;xs=m[i]>=s[i] or c[i]>m[i] or ax[i]<20
        elif name=='C':
            if 0<i-compressed<=8:
                long=b.close>max(x.high for x in bars[i-20:i]) and i-last>=32
                short=b.close<min(x.low for x in bars[i-20:i]) and i-last>=32
            if width[i]<0.5*median(width[i-120:i]):compressed=i
            xl=c[i]<f[i];xs=c[i]>f[i]
        elif name=='D':
            regime=ax[i]<=20 and abs(m[i]-s[i])/a[i]<=1
            long=regime and rs[i-1]<=30<rs[i];short=regime and rs[i-1]>=70>rs[i]
            xl=rs[i]>=50 or ax[i]>=25;xs=rs[i]<=50 or ax[i]>=25
        else:
            el=f[i]>m[i] and c[i]>f[i] and h1[i]==1 and h4[i]==1
            es=f[i]<m[i] and c[i]<f[i] and h1[i]==-1 and h4[i]==-1
            long=el and not previous_long and i-last>=64;short=es and not previous_short and i-last>=64
            previous_long,previous_short=el,es
            xl=f[i]<=m[i] or c[i]<f[i] or h1[i]!=1 or h4[i]!=1
            xs=f[i]>=m[i] or c[i]>f[i] or h1[i]!=-1 or h4[i]!=-1
        if long or short:last=i
        v=D(str(a[i]));result.append(Decision('LONG' if long else 'SHORT' if short else None,v*3,v*6,xl,xs,'LAB3_'+name if long or short else 'NO_SIGNAL'))
    trailing=[None if v is None or v<=0 else D(str(v))*3 for v in a] if name=='A' else None
    return result,trailing


def labels(bars,deadline=None):
    ax=adx(bars,14)[0];av=atr(bars,14);norm=[None if v is None else v/float(b.close) for b,v in zip(bars,av)]
    out=[]
    for i in range(len(bars)):
        if deadline is not None and time.monotonic()>deadline:raise ValueError('COMPUTE_TIMEOUT')
        direction='UNKNOWN' if ax[i] is None else 'TREND' if ax[i]>=25 else 'RANGE' if ax[i]<=20 else 'TRANSITION'
        vol='UNKNOWN' if i<514 else 'HIGH' if norm[i]>=median(norm[i-500:i]) else 'LOW'
        out.append(direction+'_'+vol)
    return out

"""Causal research indicators, separately implemented; Aura formulas untouched."""
from math import isfinite
from .models import LabError


def ema(values,n):
    out=[None]*len(values)
    if len(values)<n:return out
    value=sum(values[:n])/n;out[n-1]=value
    for i in range(n,len(values)):
        value+=(values[i]-value)*2/(n+1);out[i]=value
    return out


def rsi(values,n=14):
    out=[None]*len(values)
    if len(values)<=n:return out
    changes=[b-a for a,b in zip(values,values[1:])]
    gain=sum(max(c,0) for c in changes[:n])/n;loss=sum(max(-c,0) for c in changes[:n])/n
    def score():return 50 if gain==loss==0 else 100 if loss==0 else 100-100/(1+gain/loss)
    out[n]=score()
    for i in range(n+1,len(values)):
        gain=(gain*(n-1)+max(changes[i-1],0))/n;loss=(loss*(n-1)+max(-changes[i-1],0))/n;out[i]=score()
    return out


def atr(bars,n=14):
    ranges=[float(b.high-b.low) if i==0 else max(float(b.high-b.low),abs(float(b.high-bars[i-1].close)),abs(float(b.low-bars[i-1].close))) for i,b in enumerate(bars)]
    out=[None]*len(bars)
    if len(bars)<n:return out
    value=sum(ranges[:n])/n;out[n-1]=value
    for i in range(n,len(bars)):value=(value*(n-1)+ranges[i])/n;out[i]=value
    return out


def adx(bars,n=14):
    size=len(bars);out=[None]*size;plus=[None]*size;minus=[None]*size
    if size<2*n:return out,plus,minus
    tr=[];pd=[];md=[]
    for a,b in zip(bars,bars[1:]):
        up=float(b.high-a.high);down=float(a.low-b.low)
        tr.append(max(float(b.high-b.low),abs(float(b.high-a.close)),abs(float(b.low-a.close))))
        pd.append(up if up>down and up>0 else 0);md.append(down if down>up and down>0 else 0)
    smooth_tr=sum(tr[:n]);smooth_p=sum(pd[:n]);smooth_m=sum(md[:n]);dx=[]
    for i in range(n,size):
        if i>n:
            smooth_tr=smooth_tr-smooth_tr/n+tr[i-1];smooth_p=smooth_p-smooth_p/n+pd[i-1];smooth_m=smooth_m-smooth_m/n+md[i-1]
        p=100*smooth_p/smooth_tr if smooth_tr else 0;m=100*smooth_m/smooth_tr if smooth_tr else 0
        plus[i],minus[i]=p,m;dx.append(100*abs(p-m)/(p+m) if p+m else 0)
        if i==2*n-1:out[i]=sum(dx[:n])/n
        elif i>2*n-1:out[i]=(out[i-1]*(n-1)+dx[-1])/n
    return out,plus,minus

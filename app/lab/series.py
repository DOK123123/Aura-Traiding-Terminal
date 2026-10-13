"""Pure closed UTC aggregation/segmentation shared by offline and online analysis.

Moved verbatim from existing research helpers. No I/O or execution dependency.
"""
from decimal import Decimal as D
from .models import Bar


def higher(bars,step):
    result=[];group=[];key=None
    for b in bars:
        bucket=b.time//step*step
        if key!=bucket:group=[];key=bucket
        group.append(b)
        if b.time+900==bucket+step and len(group)==step//900 and group[0].time==bucket:
            result.append(Bar(bucket,group[0].open,max(x.high for x in group),min(x.low for x in group),b.close,sum((x.volume for x in group),D(0))))
    return result



def split_parts(bars,step):
    result=[];left=0
    for i in range(1,len(bars)):
        if bars[i].time-bars[i-1].time != step: result.append(bars[left:i]);left=i
    if bars:result.append(bars[left:])
    return result


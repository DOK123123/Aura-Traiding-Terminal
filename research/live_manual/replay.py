"""Offline prefix replay of live browser rules vs unchanged closed Analyst.

Reads only the supplied local official Bitget minute archives. No network, ledger,
production or account dependency. Intraminute path and actual bid/ask unavailable.
"""
import argparse
from collections import Counter,deque
import csv
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile
from app.models import Candle
from app.aura_trader5_scenarios import assess

ROOT=Path(__file__).resolve().parents[2]
STEPS={'1m':60,'5m':300,'15m':900,'1h':3600,'4h':14400}

def epoch(s):return int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp())

def load(folder):
    manifest=json.loads((folder/'manifest.json').read_text());bars=[];sources=[]
    if manifest.get('source')!='BITGET_USDT_FUTURES_BTCUSDT' or manifest.get('product_type')!='USDT-FUTURES' or not 1<=len(manifest.get('files',[]))<=12:raise ValueError('SOURCE_OR_LIMIT')
    for item in manifest['files']:
        name=item.get('path',item.get('file'))
        if name is None:raise ValueError('INPUT_MANIFEST_PATH_REQUIRED')
        p=(folder/name).resolve()
        if p.parent!=folder.resolve() or not p.name.endswith('.zip'):raise ValueError('LOCAL_OFFICIAL_ZIP_REQUIRED')
        if p.stat().st_size>128*1024*1024:raise ValueError('ARCHIVE_LIMIT')
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        if digest!=item['sha256']:raise ValueError('INPUT_HASH_MISMATCH')
        with zipfile.ZipFile(p) as z:
            if len(z.namelist())!=1 or z.infolist()[0].file_size>100*1024*1024:raise ValueError('ARCHIVE_LIMIT')
            with z.open(z.namelist()[0]) as raw:
                for row in csv.DictReader(io.TextIOWrapper(raw,encoding='utf-8-sig')):
                    b=Candle(int(row['timestamp']),*[float(row[k]) for k in ('open','high','low','close','basevolume')]);bars.append(b)
        if len(bars)>600000:raise ValueError('ROW_LIMIT')
        sources.append(dict(file=p.name,sha256=digest,url=item.get('url',item.get('source_url'))))
    bars.sort(key=lambda b:b.time)
    if any(b.time%60 or b.volume is None for b in bars) or any(b.time-a.time!=60 for a,b in zip(bars,bars[1:])):raise ValueError('GAP_DUPLICATE_OR_TIME')
    return bars,sources

class Book:
    def __init__(self):self.closed={tf:deque(maxlen=200) for tf in STEPS};self.partial={}
    def open(self,b):
        for tf,step in STEPS.items():
            at=b.time//step*step;p=self.partial.get(tf)
            if p and p.time!=at:self.closed[tf].append(p);p=None
            self.partial[tf]=Candle(at,p.open if p else b.open,max(p.high,b.open) if p else b.open,min(p.low,b.open) if p else b.open,b.open,p.volume if p else 0)
    def finish(self,b):
        for tf,p in self.partial.items():self.partial[tf]=Candle(p.time,p.open,max(p.high,b.high),min(p.low,b.low),b.close,p.volume+b.volume)

class Simulator:
    def __init__(self,protocol,mult):self.p=protocol;self.mult=mult;self.cash=10000.;self.position=None;self.pending=None;self.used=set();self.trades=[];self.equity=[];self.rejected=Counter();self.day=None;self.baseline=10000.
    def fill(self,price,long,entry):
        sign=(1 if long else -1)*(1 if entry else -1)
        return price*(1+sign*(self.p['adverse_slippage_per_side']+self.p['modeled_spread_bps']/20000)*self.mult)
    def close(self,price,at,reason):
        p=self.position;x=self.fill(price,p['side']=='LONG',False);gross=(x-p['entry'])*p['qty']*(1 if p['side']=='LONG' else -1);fee=x*p['qty']*self.p['fee_per_side']*self.mult;net=gross-fee-p['entry_fee'];self.cash+=gross-fee;self.trades.append(dict(**p,exit=x,exit_at=at,reason=reason,net=net,fees=fee+p['entry_fee']));self.position=None
    def bar(self,b):
        if self.day!=b.time//86400:self.day=b.time//86400;self.baseline=self.cash
        if not self.position and self.pending and b.time>=self.pending['available_at']+60:
            p=self.pending;self.pending=None;long=p['side']=='LONG';e=self.fill(b.open,long,True);stop=p['stop_loss'];target=p['take_profit'];zone=p['entry_zone']
            if b.volume<=0 or self.cash<=9000 or not (zone['low']<=e<=zone['high']) or not (stop<e<target if long else target<e<stop):self.rejected['ENTRY_RISK_OR_ZONE']+=1
            else:
                stopfill=self.fill(stop,long,False);unit=abs(e-stopfill)+(e+stopfill)*self.p['fee_per_side']*self.mult;budget=min(self.cash*.005,max(0,self.baseline*.02+self.cash-self.baseline),max(0,self.cash-9000));qty=min(2000/e,budget/unit);qty=int(qty*10000)/10000
                if qty<.0001 or qty*e<5:self.rejected['RISK_OR_MIN_SIZE']+=1
                else:
                    fee=e*qty*self.p['fee_per_side']*self.mult;self.cash-=fee;self.position=dict(id=p['id'],side=p['side'],entry=e,qty=qty,stop=stop,target=target,entry_fee=fee,entry_at=b.time)
        p=self.position
        if p and b.volume>0:
            long=p['side']=='LONG';stop=b.low<=p['stop'] if long else b.high>=p['stop'];target=b.high>=p['target'] if long else b.low<=p['target']
            if stop:self.close(min(b.open,p['stop']) if long else max(b.open,p['stop']),b.time+60,'STOP_LOSS')
            elif target:self.close(p['target'],b.time+60,'TAKE_PROFIT')
        equity=self.cash+((b.close-p['entry'])*p['qty']*(1 if p['side']=='LONG' else -1) if (p:=self.position) else 0);self.equity.append(equity)
    def signal(self,result,at,key):
        if result.get('state') not in ('LONG','SHORT') or not result.get('scenario'):return
        if key in self.used:return
        self.used.add(key)
        if not self.position and not self.pending:self.pending=dict(result['scenario'],side=result['state'],available_at=at,id=key)
    def metrics(self):
        peak=10000;dd=0
        for e in self.equity:peak=max(peak,e);dd=max(dd,(peak-e)/peak*100)
        win=sum(t['net'] for t in self.trades if t['net']>0);loss=-sum(t['net'] for t in self.trades if t['net']<0);n=len(self.trades)
        return dict(trades=n,long=sum(t['side']=='LONG' for t in self.trades),short=sum(t['side']=='SHORT' for t in self.trades),net_pnl=self.cash-10000,return_pct=(self.cash/10000-1)*100,profit_factor=win/loss if loss else None,win_rate_pct=100*sum(t['net']>0 for t in self.trades)/n if n else None,expectancy=(self.cash-10000)/n if n else None,max_drawdown_pct=dd,rejections=dict(self.rejected))

def main():
    args=argparse.ArgumentParser();args.add_argument('--input',type=Path,required=True);args.add_argument('--output',type=Path,required=True);opt=args.parse_args()
    if opt.output.exists():raise ValueError('NEW_OUTPUT_REQUIRED')
    protocol=json.loads((Path(__file__).with_name('protocol.json')).read_text());bars,sources=load(opt.input);start,end=map(epoch,[protocol['sample_start_inclusive'],protocol['sample_end_exclusive']]);
    if bars[0].time>start-201*14400 or bars[-1].time+60<end:raise ValueError('INSUFFICIENT_WARMUP_OR_SAMPLE')
    book=Book();counts=Counter();reasons=Counter();sim={(kind,m):Simulator(protocol,m) for kind in ('LIVE','CLOSED') for m in (1,1.5,2)};last_live={};last_closed={};withdrawals=0;events=[];proc=subprocess.Popen(['node',str(Path(__file__).with_name('bridge.cjs'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
      for b in bars:
        if b.time>=end:break
        book.open(b)
        if b.time>=start and all(len(w)==200 for w in book.closed.values()):
            now=b.time+1;snapshot=dict(status='LIVE',windows={tf:dict(bars=[asdict(x) for x in book.closed[tf]]+[asdict(book.partial[tf])],received_at=now,event_at=now) for tf in STEPS},quote=dict(source='BITGET_USDT_FUTURES_BTCUSDT',bid=b.open*.9999,ask=b.open*1.0001,last=b.open,time=now,received_at=now))
            proc.stdin.write(json.dumps(dict(snapshot=snapshot,now=now),separators=(',',':'))+'\n');proc.stdin.flush();live=json.loads(proc.stdout.readline());closed=assess({tf:list(book.closed[tf]) for tf in ('5m','15m','1h','4h')},now)
            # A preliminary plan withdrawn before its 5m close is counted, never hidden.
            key=str(b.time//300*300)
            if last_live.get(key) in ('LONG','SHORT') and live['state']!=last_live[key]:withdrawals+=1
            last_live[key]=live['state'];counts['observations']+=1;counts['live_'+live['state']]+=1;counts['closed_'+closed['state']]+=1;reasons.update(live['reasons'])
            if live['state']!='WAIT' or closed['state']!='WAIT':events.append(dict(at=now,live=live['state'],closed=closed['state'],reason=';'.join(live['reasons'])))
            for (kind,m),s in sim.items():
                s.signal(live if kind=='LIVE' else closed,now,kind+key);s.bar(b)
        book.finish(b)
      for s in sim.values():
        if s.position:s.close(bars[[x.time for x in bars].index(end-60)].close,end,'TERMINAL_ESTIMATE');s.equity.append(s.cash)
      opt.output.mkdir(parents=True);summary=dict(protocol=protocol,protocol_sha256=hashlib.sha256(Path(__file__).with_name('protocol.json').read_bytes()).hexdigest(),code_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'static/manual-live-analysis.js',ROOT/'research/live_manual/bridge.cjs',ROOT/'app/aura_trader5_scenarios.py',ROOT/'app/aura_trader5_analysis.py',ROOT/'app/aura_trader5_technical.py']},sources=sources,counts=dict(counts),preliminary_withdrawals=withdrawals,live_wait_reasons=dict(reasons),metrics={kind+'_cost'+str(m):s.metrics() for (kind,m),s in sim.items()},verdict='INSUFFICIENT_EVIDENCE',production_changed=False)
      (opt.output/'summary.json').write_text(json.dumps(summary,indent=2))
      for name,rows in [('signals',events)]+[(kind+'-cost'+str(m)+'-trades',s.trades) for (kind,m),s in sim.items()]:
        with (opt.output/(name+'.csv')).open('w') as f:
          writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['id']);writer.writeheader();writer.writerows(rows)
      print(json.dumps(summary['counts']));print(json.dumps(summary['metrics']))
    finally:
      proc.stdin.close();proc.terminate();proc.wait(timeout=5)
if __name__=='__main__':main()

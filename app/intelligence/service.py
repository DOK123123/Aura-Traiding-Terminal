"""Durable owner-confirmed replay portfolio. Network-free, no Auto/Paper DB access."""
from bisect import bisect_left
from dataclasses import replace
from decimal import Decimal as D
import hashlib,json,sqlite3,time,uuid
from pathlib import Path
from contextlib import contextmanager

from app.lab.models import Bar,Baseline,canonical,validate_series,money,text,quantity,precise
from app.lab.execution import simulate,fee,fill
from app.lab.strategies import Decision
from .analysis import analyze,CONFIG

DATA=Path(__file__).parent/'data/demo.json'
DATA_SHA='9390ab14a33f93570ac4b83f9f91387372bd950cb729581735a9e62fbf1f6249'


class IntelligenceError(Exception):pass


class Service:
    def __init__(self,path,clock=time.time):
        self.path=Path(path);self.clock=clock
        raw=DATA.read_bytes()
        if len(raw)>3*1024*1024 or hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise IntelligenceError('HISTORY_UNAVAILABLE')
        self.pack=json.loads(raw);self.bars=[Bar.restore(b) for b in self.pack['bars']]
        self.software_sha=hashlib.sha256(Path(__file__).read_bytes()+(Path(__file__).parents[1]/'lab/execution.py').read_bytes()+Path(__file__).with_name('analysis.py').read_bytes()+Path(__file__).with_name('patterns.py').read_bytes()+canonical(CONFIG)).hexdigest()
        validate_series(self.bars,900,self.pack['replay_end'])
        if self.pack['config']!=CONFIG or any(r['resolved_at']>=self.pack['training_end'] for r in self.pack['index']):raise IntelligenceError('HISTORY_UNAVAILABLE')
        self.frames={'15m':self.bars}
        for tf,step in [('1h',3600),('4h',14400)]:self.frames[tf]=self.aggregate(self.bars,step)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:db.execute('CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')

    @staticmethod
    def aggregate(bars,step):
        output=[];group=[];key=None
        for b in bars:
            k=b.time//step*step
            if k!=key:key=k;group=[]
            group.append(b)
            if b.time+900==k+step and len(group)==step//900 and group[0].time==k:
                output.append(Bar(k,group[0].open,max(x.high for x in group),min(x.low for x in group),b.close,sum((x.volume for x in group),D(0))))
        return output

    @contextmanager
    def db(self):
        connection=sqlite3.connect(self.path,timeout=3)
        try:
            connection.execute('BEGIN IMMEDIATE');yield connection;connection.commit()
        except BaseException:connection.rollback();raise
        finally:connection.close()

    def create(self,timeframe,candle_time,manual_research=False):
        bs=self.frames[timeframe];index=bisect_left([b.time for b in bs],candle_time)
        if index>=len(bs) or bs[index].time!=candle_time or index<200 or not self.pack['replay_start']<=candle_time<self.pack['replay_end']:raise IntelligenceError('DATE_UNAVAILABLE')
        session=dict(id=str(uuid.uuid4()),timeframe=timeframe,cursor=index,start=index,manual_research=manual_research,confirmed=[],proposal=None,events=[dict(state='DETECTED'),dict(state='ANALYZED')],dataset_sha256=DATA_SHA,software_sha256=self.software_sha)
        with self.db() as db:
            if db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]>=20:raise IntelligenceError('SESSION_LIMIT')
            db.execute('INSERT INTO sessions VALUES(?,?)',(session['id'],json.dumps(session)))
        return self.state(session['id'])

    def load(self,db,sid):
        row=db.execute('SELECT payload FROM sessions WHERE id=?',(sid,)).fetchone()
        if row is None:raise IntelligenceError('NOT_FOUND')
        session=json.loads(row[0])
        if session['dataset_sha256']!=DATA_SHA:raise IntelligenceError('DATASET_CHANGED')
        if session.get('software_sha256')!=self.software_sha:raise IntelligenceError('SOFTWARE_CHANGED')
        return session

    def save(self,db,s):db.execute('UPDATE sessions SET payload=? WHERE id=?',(json.dumps(s),s['id']))

    def portfolio(self,s):
        bs=self.frames[s['timeframe']];step={'15m':900,'1h':3600,'4h':14400}[s['timeframe']]
        ds=[Decision() for _ in bs]
        for p in s['confirmed']:
            ds[p['cursor']]=Decision(p['direction'],D(p['stop_distance']),D(p['target_distance']),reason='OWNER_CONFIRMED_REPLAY_HYPOTHESIS')
            deadline=p['cursor']+CONFIG['horizon_days']*86400//step
            if deadline<len(ds):
                previous=ds[deadline]
                ds[deadline]=replace(previous,exit_long=True,exit_short=True)
        value=simulate(bs,ds,s['start'],s['cursor']+1,step,Baseline(),time.monotonic()+3,close_at_end=False)
        if s['cursor']+1==len(bs) and value.get('open_position') is not None:value['dataset_ended_with_open_position']=True
        return value

    def render(self,s):
        bs=self.frames[s['timeframe']];context=analyze(bs[max(0,s['cursor']-249):s['cursor']+1],self.pack['index'],s['timeframe']);value=self.portfolio(s)
        p=s['proposal']
        if p and p['status']=='PROPOSED' and self.clock()>p['expires_at']:p['status']='EXPIRED'
        if p and p['status']=='CONFIRMED' and s['cursor']>p['cursor']:
            filled=any(t['signal_time']==p['candle_close_time'] for t in value['trades']) or value.get('open_position') is not None and value['open_position']['signal_time']==p['candle_close_time']
            p['status']='PAPER_EXECUTED' if filled else 'REJECTED'
            s['events'].append(dict(state=p['status'],id=p['id']))
        if value.get('open_position') is not None:context.update(strategy='WAIT',reason='POSITION_ALREADY_OPEN')
        s['journal']=value['trades']
        s['portfolio_snapshot']=value
        return dict(session_id=s['id'],mode='REPLAY_PAPER_ONLY',real_money_execution='DISABLED',automatic_execution=False,
            timeframe=s['timeframe'],analysis=context,proposal=p,portfolio=value,manual_research=s['manual_research'],
            source=self.pack['source'],dataset_sha256=DATA_SHA,config=CONFIG,
            candles=[b.data() for b in bs[max(0,s['cursor']-49):s['cursor']+1]],events=s['events'][-30:],
            last_candle_time=bs[s['cursor']].time,can_advance=s['cursor']+1<len(bs) and s['cursor']-s['start']<512)

    def state(self,sid):
        with self.db() as db:
            s=self.load(db,sid);data=self.render(s);self.save(db,s);return data

    @precise
    def proposal(self,sid,manual=False):
        with self.db() as db:
            s=self.load(db,sid);view=self.render(s);analysis=view['analysis'];portfolio=view['portfolio']
            if not view['can_advance']:raise IntelligenceError('REPLAY_END')
            if portfolio.get('open_position') is not None or s['proposal'] and s['proposal']['status'] in ('CONFIRMED','PROPOSED'):raise IntelligenceError('POSITION_LIMIT')
            if analysis['strategy']=='WAIT' and not (manual and s['manual_research']):raise IntelligenceError(analysis['reason'])
            side=analysis['context']['direction']
            if side not in ('LONG','SHORT'):raise IntelligenceError('NO_DIRECTION')
            current=self.frames[s['timeframe']][s['cursor']];sign=1 if side=='LONG' else -1
            stop=current.close*D('.02');target=current.close*D('.04')
            # Quote estimate from known close; no fabricated OHLCV bar.
            step={'15m':900,'1h':3600,'4h':14400}[s['timeframe']]
            balance=D(portfolio['equity_curve'][-1]['balance']);entry=fill(current.close,side,True,D('.0005'))
            sl=entry-sign*stop;tp=entry+sign*target;exit_stop=fill(sl,side,False,D('.0005'))
            unit=abs(entry-exit_stop)+D('.001')*(entry+exit_stop)
            size=quantity(min((balance/D(100)-D('.00000003'))/unit,D(2000)/entry,(balance-D('.00000002'))/(entry*D('1.001'))))
            risk=money(abs(entry-exit_stop)*size,ceil=True)+fee(entry,size,D('.001'))+fee(exit_stop,size,D('.001'))
            if size<=0 or min(sl,tp)<=0 or risk>balance/100:raise IntelligenceError('RISK_REJECTED')
            plan=dict(direction=side,entry_price=text(entry),size=text(size),stop_loss=text(sl),take_profit=text(tp),risk_usdt=text(risk),risk_pct=text(money(risk/balance*100)),notional=text(money(entry*size)),entry_fee=text(fee(entry,size,D('.001'))),planned_risk_reward=text(money((money(sign*(fill(tp,side,False,D('.0005'))-entry)*size)-fee(entry,size,D('.001'))-fee(fill(tp,side,False,D('.0005')),size,D('.001')))/risk)))
            p=dict(id=str(uuid.uuid4()),status='PROPOSED',cursor=s['cursor'],direction=side,
                candle_close_time=current.time+step,stop_distance=text(stop),target_distance=text(target),
                created_at=self.clock(),expires_at=self.clock()+CONFIG['proposal_ttl_seconds'],estimate=plan,
                expected_net_value=text(money(D(str(analysis['evidence']['expectancy_after_costs']))*D(plan['notional'])/2000)) if analysis['evidence']['expectancy_after_costs'] is not None else None,
                expected_value_note='Scaled descriptive past-event mean, not a validated prediction.',
                hypothetical_manual=manual,advice='WAIT — manual research hypothesis, NOT recommendation' if manual else 'Experimental historical candidate, NOT live-validated',
                estimate_only=True,actual_fill='Next observed candle open; adverse5bps, risk rechecked',dataset_sha256=DATA_SHA)
            s['proposal']=p;s['events'].append(dict(state='PROPOSED',id=p['id']));self.save(db,s);return self.render(s)

    def decide(self,sid,pid,confirm):
        with self.db() as db:
            s=self.load(db,sid);view=self.render(s);p=s['proposal']
            if p is None or p['id']!=pid:raise IntelligenceError('PROPOSAL_CHANGED')
            if confirm and p['status'] in ('CONFIRMED','PAPER_EXECUTED'):return view
            if p['status']!='PROPOSED' or p['cursor']!=s['cursor'] or p['dataset_sha256']!=DATA_SHA:raise IntelligenceError('EXPIRED')
            if view['portfolio'].get('open_position') is not None:raise IntelligenceError('POSITION_LIMIT')
            if confirm:s['confirmed'].append(dict(p));p['status']='CONFIRMED'
            else:p['status']='REJECTED'
            s['events'].append(dict(state=p['status'],id=p['id']));self.save(db,s);return self.render(s)

    def advance(self,sid,steps=1):
        with self.db() as db:
            s=self.load(db,sid);bs=self.frames[s['timeframe']]
            if s['cursor']+steps>=len(bs) or s['cursor']+steps-s['start']>512:raise IntelligenceError('REPLAY_END')
            if s['proposal'] and s['proposal']['status']=='PROPOSED':s['proposal']['status']='EXPIRED'
            s['cursor']+=steps;view=self.render(s);self.save(db,s);return view

    def manifest(self):
        return dict(source=self.pack['source'],dataset_sha256=DATA_SHA,config=CONFIG,training_end=self.pack['training_end'],
            dates=dict(start=self.pack['replay_start'],end=self.pack['replay_end']),timeframes=list(self.frames),
            smoke=dict(candle_time=self.pack['replay_start'],timeframe='15m',kind='EXPLICIT_MANUAL_HYPOTHESIS_WITH_WAIT'),
            warning='No validated profitable strategy. Automatic/live proposals unavailable; manual replay hypothesis requires explicit opt-in and separate confirmation.')

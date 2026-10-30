"""Dedicated SQLite observation journal. No wallets, order tables or account writes."""
from contextlib import contextmanager
import hashlib
import json
import math
import sqlite3
import threading
from pathlib import Path

from .engine import FAMILIES, Prepared, VERSION, net_rr
from .market import SOURCE, STEPS, fresh_quote
from .outcomes import cashflow

MODEL_HASH = hashlib.sha256(Path(__file__).with_name('engine.py').read_bytes()+Path(__file__).with_name('rules.json').read_bytes()).hexdigest()
LIVE_INPUT_CONTRACT = 'BITGET_NATIVE_260_CLOSED_BARS_V1'


def validated(plan, registry):
    # The shipped registry is empty. HTTP and environment cannot grant eligibility.
    if not isinstance(registry,dict) or not isinstance(registry.get('approved'),list):
        return False
    return any(isinstance(x,dict) and x.get('status')=='VALIDATED' and x.get('independent') is True
               and x.get('input_contract')==LIVE_INPUT_CONTRACT
               and x.get('model_sha256')==MODEL_HASH and isinstance(x.get('evidence_sha256'),str) and len(x['evidence_sha256'])==64 and all(c in '0123456789abcdef' for c in x['evidence_sha256'])
               and all(x.get(k)==plan.get(k) for k in ('strategy','frame','direction','variant'))
               for x in registry.get('approved', []))


def forward_outcome(record, bars, funding):
    p=record['plan'];sign=1 if p['direction']=='LONG' else -1
    after=[b for b in bars if b[0]+p['step']>record['detected_at']]
    start=int(record['detected_at']//p['step'])*p['step']
    result={'outcome':'OPEN','entered':True,'entry_time':record['detected_at'],
            'entry_fill':record['quote']['ask' if sign==1 else 'bid']*(1+sign*.0005),
            'exit_time':None,'pnl_usdt':None,'r':None,'note':'PUBLIC_QUOTE_HYPOTHESIS_NOT_EXECUTION'}
    if not after:
        return result
    if after[0][0]!=start or any(b[0]-a[0]!=p['step'] for a,b in zip(after,after[1:])):
        return {**result,'outcome':'UNKNOWN','note':'RECOVERY_CANDLE_GAP'}
    if not funding or funding[0][0]>record['detected_at'] or any(b[0]-a[0]>28800 for a,b in zip(funding,funding[1:])):
        return {**result,'outcome':'UNKNOWN','note':'FUNDING_COVERAGE_UNVERIFIED'}
    for i,b in enumerate(after[:p['hold_bars']]):
        # The detection candle has pre-detection extremes. Never certify an intrabar winner from them.
        q=1-sign*.0001
        op,high,low,close=b[1]*q,b[2]*q,b[3]*q,b[4]*q
        sl=low<=p['sl'] if sign==1 else high>=p['sl']
        tp=high>=p['tp'] if sign==1 else low<=p['tp']
        if i==0 and (sl or tp):
            return {**result,'outcome':'UNKNOWN','note':'DETECTION_BAR_TOUCH_SEQUENCE_UNKNOWN'}
        price=outcome=None
        if i>0 and sign*(op-p['sl'])<=0:price,outcome=op,'SL'
        elif i>0 and sign*(op-p['tp'])>=0:price,outcome=p['tp'],'TP'
        elif sl:price,outcome=p['sl'],'SL'
        elif tp:price,outcome=p['tp'],'TP'
        elif i==p['hold_bars']-1:price,outcome=close,'TIMEOUT'
        if outcome:
            if funding[-1][0]<b[0]+p['step']-28800:
                return {**result,'outcome':'UNKNOWN','note':'FUNDING_TAIL_UNVERIFIED'}
            # Spread/slippage are reserves, not true historical executions.
            fill=price*(1-sign*.0005)
            result.update(outcome=outcome,exit_time=b[0],exit_fill=fill,
                          note='BOTH_TOUCHED_SL_FIRST' if sl and tp else 'CLOSED_CANDLE_OBSERVATION')
            result.update(cashflow(p,result['entry_fill'],fill,record['detected_at'],b[0],after[:i+1],funding))
            return result
    return result


class Store:
    def __init__(self, path):
        if str(path).startswith('file:') or '://' in str(path):
            raise ValueError('LOCAL_OBSERVER_DB_ONLY')
        self.path=str(path);self.lock=threading.RLock()
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS watermarks (frame TEXT PRIMARY KEY, cutoff INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, frame TEXT NOT NULL, at REAL NOT NULL,
            expires REAL NOT NULL, state TEXT NOT NULL, technical INTEGER NOT NULL, payload TEXT NOT NULL,
            outcome TEXT NOT NULL DEFAULT 'PENDING', result TEXT);
            CREATE TABLE IF NOT EXISTS alerts (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
            at REAL NOT NULL, expires REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS event_at ON events(at);
            CREATE INDEX IF NOT EXISTS event_pending ON events(frame,outcome,technical);
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);''')

    @contextmanager
    def connection(self):
        with self.lock:
            db=sqlite3.connect(self.path,timeout=5)
            db.row_factory=sqlite3.Row
            try:
                db.execute('PRAGMA journal_mode=WAL')
                with db:yield db
            finally:db.close()

    def invalidate(self, now, reason='DATA_UNAVAILABLE'):
        with self.connection() as db:
            db.execute("UPDATE events SET state='CANCELLED_DATA' WHERE state IN ('WATCH','CONFIRMED')")
            db.execute("INSERT OR REPLACE INTO meta VALUES ('status',?)",(json.dumps({'state':'NO TRADE','reason':reason,'at':now}),))

    def observe(self, snapshot, funding, now, registry):
        if snapshot.get('source')!=SOURCE or not fresh_quote(snapshot.get('quote',{}),now):
            raise ValueError('UNVERIFIED_OBSERVER_SNAPSHOT')
        frame,step,bars=snapshot['frame'],snapshot['step'],snapshot['bars']
        if frame not in STEPS or step!=STEPS[frame]:raise ValueError('OBSERVER_FRAME_MISMATCH')
        prepared=Prepared(bars,frame)
        cutoff=bars[-1][0]+step
        if cutoff!=int(now//step)*step:
            raise ValueError('OBSERVER_STALE_CANDLES')
        plans=[]
        for family in FAMILIES:
            plans.extend(prepared.plans(len(bars)-1,family,cutoff=cutoff,watch=True))
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE events SET state='EXPIRED' WHERE expires<=? AND state IN ('WATCH','CONFIRMED')",(now,))
            for old in db.execute("SELECT id,payload FROM events WHERE frame=? AND state IN ('WATCH','CONFIRMED')",(frame,)).fetchall():
                p=json.loads(old['payload'])['plan'];q=snapshot['quote'];ref=q['ask' if p['direction']=='LONG' else 'bid']
                rr=net_rr(ref,p['sl'],p['tp'],p['direction'],step,p['hold_bars'],q['ask']-q['bid'])
                if not p['zone'][0]<=ref<=p['zone'][1] or rr is None or rr<1.5:
                    db.execute("UPDATE events SET state='CANCELLED_ENTRY' WHERE id=?",(old['id'],))
            pending=db.execute("SELECT * FROM events WHERE frame=? AND technical=1 AND outcome IN ('PENDING','OPEN') ORDER BY at LIMIT 1000",(frame,)).fetchall()
            for row in pending:
                record=json.loads(row['payload'])
                result=forward_outcome(record,bars,funding)
                db.execute('UPDATE events SET outcome=?,result=? WHERE id=?',(result['outcome'],json.dumps(result),row['id']))
            wm=db.execute('SELECT cutoff FROM watermarks WHERE frame=?',(frame,)).fetchone()
            if wm and wm[0]>=cutoff:
                return
            db.execute('INSERT OR REPLACE INTO watermarks VALUES (?,?)',(frame,cutoff))
            for p in plans:
                p['step']=step;p['model_sha256']=MODEL_HASH
                p['input_contract']=LIVE_INPUT_CONTRACT
                q=snapshot['quote'];reference=q['ask' if p['direction']=='LONG' else 'bid']
                rr=net_rr(reference,p['sl'],p['tp'],p['direction'],step,p['hold_bars'],q['ask']-q['bid'])
                entry_valid=p['zone'][0]<=reference<=p['zone'][1] and rr is not None and rr>=1.5 and now<p['valid_until']
                evidence=validated(p,registry)
                funding_ready=bool(len(funding)>=2 and funding[0][0]<=now and 0<=now-funding[-1][0]<=28800 and all(type(t) is int and math.isfinite(rate) and -1<rate<1 and t<=now for t,rate in funding) and all(0<b[0]-a[0]<=28800 for a,b in zip(funding,funding[1:])))
                state='CONFIRMED' if evidence and funding_ready and p['technical_trigger'] and entry_valid else 'WATCH' if entry_valid else 'NO TRADE'
                p['statistical_status']='VALIDATED' if evidence else 'UNVALIDATED'
                p['net_rr_at_quote']=rr
                record={'plan':p,'quote':q,'detected_at':now,'state':state,'reason':'RULES_AND_INDEPENDENT_EDGE' if state=='CONFIRMED' else 'RESEARCH_ONLY_NO_VALIDATED_EDGE' if state=='WATCH' else 'ENTRY_CONDITIONS_FAILED',
                        'probability_tp_before_sl':None,'scope':'PUBLIC_OBSERVATION_ONLY','research':not evidence}
                event_id=hashlib.sha256((MODEL_HASH+p['id']).encode()).hexdigest()
                inserted=db.execute('INSERT OR IGNORE INTO events(id,frame,at,expires,state,technical,payload,outcome) VALUES (?,?,?,?,?,?,?,?)',
                    (event_id,frame,now,p['valid_until'],state,int(p['technical_trigger'] and entry_valid),json.dumps(record),'PENDING' if p['technical_trigger'] and entry_valid else 'NOT_TRIGGERED')).rowcount
                if inserted and state=='CONFIRMED':
                    db.execute('INSERT OR IGNORE INTO alerts(id,at,expires) VALUES (?,?,?)',(event_id,now,min(now+30,p['valid_until'])))
            db.execute("INSERT OR REPLACE INTO meta VALUES ('status',?)",(json.dumps({'state':'READ_ONLY','at':now}),))
            db.execute("DELETE FROM events WHERE id IN (SELECT id FROM events WHERE state NOT IN ('WATCH','CONFIRMED') AND outcome NOT IN ('PENDING','OPEN') ORDER BY at DESC LIMIT -1 OFFSET 100000)")
            # Watermarks survive retention; terminal records may be pruned without replaying alerts.
            db.execute("DELETE FROM events WHERE at<? AND state NOT IN ('WATCH','CONFIRMED') AND outcome NOT IN ('PENDING','OPEN')",(now-180*86400,))

    def snapshot(self, now, quotes, error=None):
        fresh_frames={frame for frame,q in quotes.items() if fresh_quote(q,now)}
        with self.connection() as db:
            records=[]
            for row in db.execute('SELECT * FROM events ORDER BY at DESC,id LIMIT 200'):
                p=json.loads(row['payload']);state=row['state']
                if state in ('WATCH','CONFIRMED') and (row['expires']<=now or row['frame'] not in fresh_frames):state='NO TRADE'
                if state in ('WATCH','CONFIRMED'):
                    plan=p['plan'];q=quotes[row['frame']];ref=q['ask' if plan['direction']=='LONG' else 'bid']
                    rr=net_rr(ref,plan['sl'],plan['tp'],plan['direction'],plan['step'],plan['hold_bars'],q['ask']-q['bid'])
                    if not plan['zone'][0]<=ref<=plan['zone'][1] or rr is None or rr<1.5:state='NO TRADE'
                records.append({'id':row['id'],'state':state,'recorded_state':row['state'],**{k:p[k] for k in ('plan','quote','detected_at','reason','research')},
                                'outcome':row['outcome'],'result':json.loads(row['result']) if row['result'] else None})
            current=[r for r in records if r['state'] in ('WATCH','CONFIRMED')]
            state='CONFIRMED' if any(r['state']=='CONFIRMED' for r in current) else 'WATCH' if current else 'NO TRADE'
            alerts=[dict(r) for r in db.execute('SELECT * FROM alerts WHERE expires>? ORDER BY seq DESC LIMIT 100',(now,))]
            alerts=[a for a in alerts if any(r['id']==a['id'] and r['state']=='CONFIRMED' for r in current)]
        return {'scope':'AURA6_PUBLIC_OBSERVER_ONLY','source':SOURCE,'state':state if fresh_frames and not error else 'NO TRADE',
                'reason':error or ('NO_VALIDATED_EDGE' if not any(r['state']=='CONFIRMED' for r in current) else 'INDEPENDENT_EDGE_REQUIRED'),
                'server_time':now,'fresh_frames':sorted(fresh_frames),'quotes':{k:v for k,v in quotes.items() if k in fresh_frames},
                'records':records,'alerts':alerts if not error else [],'model_sha256':MODEL_HASH,
                'account_connected':False,'execution_enabled':False,'probability_tp_before_sl':None}

"""Dedicated SQLite observation journal. No wallets, order tables or account writes."""
from contextlib import contextmanager
import hashlib
import json
import math
import sqlite3
import threading
from pathlib import Path

from .engine import FAMILIES, Prepared, VERSION, RULES, net_rr
from .market import SOURCE, STEPS, LIVE_WINDOW, LIVE_INPUT_CONTRACT, fresh_quote, validate_bars
from .outcomes import cashflow
from .diagnostics import explain
from .diagnostic_store import DiagnosticStore
from .costs import entry_fill, exit_fill, filled_in_zone, risk_reward
from .confidence import technical_scores, VERSION as CONFIDENCE_VERSION, SCORE_HASH

MODEL_HASH = hashlib.sha256(b''.join(Path(__file__).with_name(name).read_bytes()
                                    for name in ('engine.py','rules.json','costs.py','outcomes.py'))).hexdigest()

def evidence_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def save_confidence(db, frame, scores, input_hash, plans, quote, now):
    """Refresh executable Bid/Ask every cycle; never change the immutable input."""
    for candidate in scores:
        candidate['input_sha256']=input_hash
        candidate['model_sha256']=MODEL_HASH
        candidate['technical_trigger']=any(p['direction']==candidate['direction']
                                          and p['technical_trigger'] for p in plans)
    db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',
               ('confidence:'+frame,json.dumps(scores,allow_nan=False)))
    for candidate in scores:
        if candidate['score']<50 or not candidate['risk_gates_passed']:
            continue
        plan={'direction':candidate['direction'],'step':STEPS[frame],
              'entry':candidate['entry'],'sl':candidate['sl'],'tp':candidate['tp'],
              'hold_bars':24,'model_sha256':MODEL_HASH}
        record={'plan':plan,'quote':quote,'detected_at':now,
                'score':candidate['score'],'score_version':CONFIDENCE_VERSION,
                'score_model_sha256':SCORE_HASH,'input_sha256':input_hash,
                'scope':'HYPOTHETICAL_PUBLIC_FORWARD_ONLY'}
        db.execute('INSERT OR IGNORE INTO confidence_events(id,frame,at,payload,outcome) VALUES (?,?,?,?,?)',
                   (candidate['id'],frame,now,json.dumps(record,allow_nan=False),'PENDING'))


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
            'entry_fill':entry_fill(record['quote']['ask' if sign==1 else 'bid'],p['direction'],quoted=True),
            'exit_time':None,'pnl_usdt':None,'r':None,'note':'PUBLIC_QUOTE_HYPOTHESIS_NOT_EXECUTION'}
    if not after:
        return result
    if after[0][0]!=start or any(b[0]-a[0]!=p['step'] for a,b in zip(after,after[1:])):
        return {**result,'outcome':'UNKNOWN','note':'RECOVERY_CANDLE_GAP'}
    if not funding or funding[0][0]>record['detected_at'] or any(b[0]-a[0]>28800 for a,b in zip(funding,funding[1:])):
        return {**result,'outcome':'UNKNOWN','note':'FUNDING_COVERAGE_UNVERIFIED'}
    for i,b in enumerate(after[:p['hold_bars']]):
        # The detection candle has pre-detection extremes. Never certify an intrabar winner from them.
        q=1-sign*RULES['costs']['full_spread_bps']/2e4
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
            fill=exit_fill(price,p['direction'])
            result.update(outcome=outcome,exit_time=b[0],exit_fill=fill,
                          note='BOTH_TOUCHED_SL_FIRST' if sl and tp else 'CLOSED_CANDLE_OBSERVATION')
            result.update(cashflow(p,result['entry_fill'],fill,record['detected_at'],b[0],after[:i+1],funding,exit_at_close=outcome=='TIMEOUT'))
            return result
    return result


class Store(DiagnosticStore):
    def __init__(self, path):
        if str(path).startswith('file:') or '://' in str(path):
            raise ValueError('LOCAL_OBSERVER_DB_ONLY')
        self.path=str(path);self.lock=threading.RLock();self.model_sha256=MODEL_HASH
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
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS inputs (seq INTEGER PRIMARY KEY AUTOINCREMENT,
            frame TEXT NOT NULL, cutoff INTEGER NOT NULL, sha256 TEXT NOT NULL, payload TEXT NOT NULL,
            UNIQUE(frame,cutoff));
            CREATE TABLE IF NOT EXISTS confidence_events (id TEXT PRIMARY KEY,frame TEXT NOT NULL,
            at REAL NOT NULL,payload TEXT NOT NULL,outcome TEXT NOT NULL,result TEXT);
            CREATE INDEX IF NOT EXISTS confidence_pending ON confidence_events(frame,outcome);''')
            self.init_diagnostics(db)

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
        if len(bars)!=LIVE_WINDOW:raise ValueError('OBSERVER_WINDOW_MISMATCH')
        validate_bars(bars,step)
        prepared=Prepared(bars,frame)
        cutoff=bars[-1][0]+step
        if cutoff!=int(now//step)*step:
            raise ValueError('OBSERVER_STALE_CANDLES')
        plans=[]
        for family in FAMILIES:
            plans.extend(prepared.plans(len(bars)-1,family,cutoff=cutoff,watch=True))
        scores=technical_scores(prepared,snapshot['quote'],now)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self.sample(db,frame,now,'LIVE',snapshot)
            db.execute("UPDATE events SET state='EXPIRED' WHERE expires<=? AND state IN ('WATCH','CONFIRMED')",(now,))
            for old in db.execute("SELECT id,payload FROM events WHERE frame=? AND state IN ('WATCH','CONFIRMED')",(frame,)).fetchall():
                p=json.loads(old['payload'])['plan'];q=snapshot['quote'];ref=q['ask' if p['direction']=='LONG' else 'bid']
                rr=net_rr(ref,p['sl'],p['tp'],p['direction'],step,p['hold_bars'],q['ask']-q['bid'])
                if not filled_in_zone(ref,p['zone'],p['direction']) or rr is None or rr<1.5:
                    db.execute("UPDATE events SET state='CANCELLED_ENTRY' WHERE id=?",(old['id'],))
            pending=db.execute("SELECT * FROM events WHERE frame=? AND technical=1 AND outcome IN ('PENDING','OPEN') ORDER BY at LIMIT 1000",(frame,)).fetchall()
            for row in pending:
                record=json.loads(row['payload'])
                result=({'outcome':'UNKNOWN','note':'MODEL_CHANGED_NO_CROSS_VERSION_OUTCOME','r':None,'pnl_usdt':None}
                        if record['plan'].get('model_sha256')!=MODEL_HASH else forward_outcome(record,bars,funding))
                db.execute('UPDATE events SET outcome=?,result=? WHERE id=?',(result['outcome'],json.dumps(result),row['id']))
            research_pending=db.execute("SELECT * FROM confidence_events WHERE frame=? AND outcome IN ('PENDING','OPEN') ORDER BY at LIMIT 1000",(frame,)).fetchall()
            for row in research_pending:
                record=json.loads(row['payload'])
                result=({'outcome':'UNKNOWN','note':'MODEL_CHANGED_NO_CROSS_VERSION_OUTCOME','r':None,'pnl_usdt':None}
                        if record.get('score_model_sha256')!=SCORE_HASH or record['plan'].get('model_sha256')!=MODEL_HASH
                        else forward_outcome(record,bars,funding))
                db.execute('UPDATE confidence_events SET outcome=?,result=? WHERE id=?',
                           (result['outcome'],json.dumps(result),row['id']))
            wm=db.execute('SELECT cutoff FROM watermarks WHERE frame=?',(frame,)).fetchone()
            if wm and wm[0]>=cutoff:
                original=db.execute('SELECT sha256 FROM inputs WHERE frame=? AND cutoff=?',(frame,cutoff)).fetchone()
                if original:save_confidence(db,frame,scores,original['sha256'],plans,snapshot['quote'],now)
                return
            db.execute('INSERT OR REPLACE INTO watermarks VALUES (?,?)',(frame,cutoff))
            # Preserve the exact parsed inputs and BASE hypotheses at first
            # detection, even when there are no setups. No silent archive/native
            # substitution; bounded export can reproduce indicator seeding.
            captured={'input_contract':LIVE_INPUT_CONTRACT,'model_sha256':MODEL_HASH,
                      'detected_at':now,'snapshot':snapshot,'funding':funding,'plans':plans}
            input_hash=evidence_hash(captured)
            db.execute('INSERT INTO inputs(frame,cutoff,sha256,payload) VALUES (?,?,?,?)',
                       (frame,cutoff,input_hash,json.dumps(captured,allow_nan=False)))
            # Score-only hypotheses live outside validated/alert/event tables.
            # The threshold is a browser display preference, never eligibility.
            save_confidence(db,frame,scores,input_hash,plans,snapshot['quote'],now)
            diagnostic_states={}
            for p in plans:
                p['step']=step;p['model_sha256']=MODEL_HASH
                p['input_contract']=LIVE_INPUT_CONTRACT
                q=snapshot['quote'];reference=q['ask' if p['direction']=='LONG' else 'bid']
                rr=net_rr(reference,p['sl'],p['tp'],p['direction'],step,p['hold_bars'],q['ask']-q['bid'])
                entry_valid=filled_in_zone(reference,p['zone'],p['direction']) and rr is not None and rr>=1.5 and now<p['valid_until']
                evidence=validated(p,registry)
                funding_ready=bool(len(funding)>=2 and funding[0][0]<=now and 0<=now-funding[-1][0]<=28800 and all(type(t) is int and math.isfinite(rate) and -1<rate<1 and t<=now for t,rate in funding) and all(0<b[0]-a[0]<=28800 for a,b in zip(funding,funding[1:])))
                state='CONFIRMED' if evidence and funding_ready and p['technical_trigger'] and entry_valid else 'WATCH' if entry_valid else 'NO TRADE'
                diagnostic_states[(p['strategy'],p['direction'])]=state
                p['statistical_status']='VALIDATED' if evidence else 'UNVALIDATED'
                p['net_rr_at_quote']=rr
                record={'plan':p,'quote':q,'detected_at':now,'input_sha256':input_hash,'state':state,'reason':'RULES_AND_INDEPENDENT_EDGE' if state=='CONFIRMED' else 'RESEARCH_ONLY_NO_VALIDATED_EDGE' if state=='WATCH' else 'ENTRY_CONDITIONS_FAILED',
                        'probability_tp_before_sl':None,'scope':'PUBLIC_OBSERVATION_ONLY','research':not evidence}
                event_id=hashlib.sha256((LIVE_INPUT_CONTRACT+MODEL_HASH+p['id']).encode()).hexdigest()
                inserted=db.execute('INSERT OR IGNORE INTO events(id,frame,at,expires,state,technical,payload,outcome) VALUES (?,?,?,?,?,?,?,?)',
                    (event_id,frame,now,p['valid_until'],state,int(p['technical_trigger'] and entry_valid),json.dumps(record),'PENDING' if p['technical_trigger'] and entry_valid else 'NOT_TRIGGERED')).rowcount
                if inserted and state=='CONFIRMED':
                    db.execute('INSERT OR IGNORE INTO alerts(id,at,expires) VALUES (?,?,?)',(event_id,now,min(now+30,p['valid_until'])))
            traced=explain(prepared,plans,now,MODEL_HASH,quote=snapshot['quote'],states=diagnostic_states)
            for row in traced:row['input_sha256']=input_hash
            db.execute('INSERT INTO diagnostic_decisions(frame,cutoff,at,model,payload) VALUES (?,?,?,?,?)',
                       (frame,cutoff,now,MODEL_HASH,json.dumps(traced,allow_nan=False)))
            db.execute("INSERT OR REPLACE INTO meta VALUES ('status',?)",(json.dumps({'state':'READ_ONLY','at':now}),))
            db.execute("DELETE FROM events WHERE id IN (SELECT id FROM events WHERE state NOT IN ('WATCH','CONFIRMED') AND outcome NOT IN ('PENDING','OPEN') ORDER BY at DESC LIMIT -1 OFFSET 100000)")
            # Watermarks survive retention; terminal records may be pruned without replaying alerts.
            db.execute("DELETE FROM events WHERE at<? AND state NOT IN ('WATCH','CONFIRMED') AND outcome NOT IN ('PENDING','OPEN')",(now-180*86400,))
            # At most 2048 inputs per frame (~7 days for 5m). Export regularly;
            # pruning is reported by the export sequence, never claimed complete.
            db.execute('DELETE FROM inputs WHERE frame=? AND seq NOT IN (SELECT seq FROM inputs WHERE frame=? ORDER BY seq DESC LIMIT 2048)',(frame,frame))
            db.execute("DELETE FROM confidence_events WHERE at<? AND outcome NOT IN ('PENDING','OPEN')",(now-180*86400,))

    def export_inputs(self, frame: str, after: int = 0, limit: int = 20) -> dict:
        if frame not in STEPS or type(after) is not int or after<0 or type(limit) is not int or not 1<=limit<=100:
            raise ValueError('INVALID_EVIDENCE_PAGE')
        with self.connection() as db:
            first=db.execute('SELECT MIN(seq) FROM inputs WHERE frame=?',(frame,)).fetchone()[0]
            rows=db.execute('SELECT * FROM inputs WHERE frame=? AND seq>? ORDER BY seq LIMIT ?', (frame,after,limit+1)).fetchall()
            items=[{'seq':r['seq'],'sha256':r['sha256'],'payload':json.loads(r['payload'])} for r in rows[:limit]]
        return {'scope':'AURA6_PARSED_NATIVE_INPUTS_NOT_PROFIT_PROOF','frame':frame,
                'items':items,'next_after':items[-1]['seq'] if items else after,'has_more':len(rows)>limit,
                'earliest_retained_seq':first,'retention_per_frame':2048,'complete_history_claimed':False}

    def snapshot(self, now, quotes, error=None):
        fresh_frames={frame for frame,q in quotes.items() if fresh_quote(q,now)}
        with self.connection() as db:
            score_rows=[]
            if not error:
                for frame in sorted(fresh_frames):
                    row=db.execute('SELECT value FROM meta WHERE key=?',('confidence:'+frame,)).fetchone()
                    if not row:continue
                    try:
                        candidates=json.loads(row['value'])
                    except (ValueError,TypeError):
                        continue  # Corrupt optional score journal must fail closed.
                    if not isinstance(candidates,list) or len(candidates)>2:continue
                    for candidate in candidates:
                        if not isinstance(candidate,dict):continue
                        quote=quotes[frame]
                        if (candidate.get('score_version')==CONFIDENCE_VERSION
                                and candidate.get('score_model_sha256')==SCORE_HASH
                                and candidate.get('model_sha256')==MODEL_HASH
                                and candidate.get('source')==SOURCE
                                and candidate.get('quote_time')==quote['time']
                                and candidate.get('quote_received_at')==quote['received_at']
                                and now<candidate.get('valid_until',0)):
                            score_rows.append(candidate)
            records=[]
            score_history=[]
            for row in db.execute('SELECT * FROM confidence_events ORDER BY at DESC,id LIMIT 100'):
                record=json.loads(row['payload'])
                score_history.append({'id':row['id'],'frame':row['frame'],'detected_at':row['at'],
                                      'score':record.get('score'),'direction':record['plan']['direction'],
                                      'score_version':record.get('score_version'),
                                      'score_model_sha256':record.get('score_model_sha256'),
                                      'input_sha256':record.get('input_sha256'),
                                      'quote_time':record['quote'].get('time'),
                                      'outcome':row['outcome'],
                                      'result':json.loads(row['result']) if row['result'] else None})
            for row in db.execute('SELECT * FROM events ORDER BY at DESC,id LIMIT 200'):
                p=json.loads(row['payload']);state=row['state']
                if state in ('WATCH','CONFIRMED') and (error or row['expires']<=now or row['frame'] not in fresh_frames or p['plan'].get('input_contract')!=LIVE_INPUT_CONTRACT or p['plan'].get('model_sha256')!=MODEL_HASH):state='NO TRADE'
                if state in ('WATCH','CONFIRMED'):
                    plan=p['plan'];q=quotes[row['frame']];ref=q['ask' if plan['direction']=='LONG' else 'bid']
                    rr=net_rr(ref,plan['sl'],plan['tp'],plan['direction'],plan['step'],plan['hold_bars'],q['ask']-q['bid'])
                    plan['net_rr_at_quote']=rr
                    plan['costs_at_quote']=risk_reward(ref,plan['sl'],plan['tp'],plan['direction'],plan['step'],plan['hold_bars'],q['ask']-q['bid'])
                    if not filled_in_zone(ref,plan['zone'],plan['direction']) or rr is None or rr<1.5:state='NO TRADE'
                records.append({'id':row['id'],'state':state,'recorded_state':row['state'],**{k:p[k] for k in ('plan','quote','detected_at','reason','research')},
                                'input_sha256':p.get('input_sha256'),
                                'outcome':row['outcome'],'result':json.loads(row['result']) if row['result'] else None})
            current=[r for r in records if r['state'] in ('WATCH','CONFIRMED')]
            state='CONFIRMED' if any(r['state']=='CONFIRMED' for r in current) else 'WATCH' if current else 'NO TRADE'
            alerts=[dict(r) for r in db.execute('SELECT * FROM alerts WHERE expires>? ORDER BY seq DESC LIMIT 100',(now,))]
            alerts=[a for a in alerts if any(r['id']==a['id'] and r['state']=='CONFIRMED' for r in current)]
            watch_alerts=[{'id':r['id'],'at':r['detected_at'],'expires':min(r['detected_at']+30,r['plan']['valid_until'])}
                          for r in current if r['state']=='WATCH' and r['research'] is True
                          and r['plan']['statistical_status']=='UNVALIDATED' and type(r['plan']['technical_trigger']) is bool
                          and 0<=now-r['detected_at']<30]
        return {'scope':'AURA6_PUBLIC_OBSERVER_ONLY','source':SOURCE,'state':state if fresh_frames and not error else 'NO TRADE',
                'reason':error or ('NO_VALIDATED_EDGE' if not any(r['state']=='CONFIRMED' for r in current) else 'INDEPENDENT_EDGE_REQUIRED'),
                'server_time':now,'fresh_frames':sorted(fresh_frames),'quotes':{k:v for k,v in quotes.items() if k in fresh_frames},
                'records':records,'alerts':alerts if not error else [],'watch_alerts':watch_alerts if not error else [],'model_sha256':MODEL_HASH,
                'journal_instance':self.journal_instance,'writer_session':self.session_id,
                'account_connected':False,'execution_enabled':False,'probability_tp_before_sl':None,
                'confidence_version':CONFIDENCE_VERSION,'confidence_candidates':score_rows,
                'confidence_history':score_history}

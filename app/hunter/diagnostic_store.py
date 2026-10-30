"""Bounded observation diagnostics in the existing local journal, never a ledger."""
from collections import Counter
import json
import uuid

from .engine import FAMILIES,VERSION
from .market import SOURCE,STEPS
from .diagnostics import utc,DIAGNOSTICS_VERSION


class DiagnosticStore:
    def init_diagnostics(self,db):
        self.session_id=uuid.uuid4().hex
        self._diagnostic_pruned_at=None
        db.executescript('''CREATE TABLE IF NOT EXISTS diagnostic_samples (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, frame TEXT NOT NULL, at REAL NOT NULL,
        status TEXT NOT NULL, session TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS diag_samples_at ON diagnostic_samples(at,frame);
        CREATE TABLE IF NOT EXISTS diagnostic_decisions (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, frame TEXT NOT NULL, cutoff INTEGER NOT NULL,
        at REAL NOT NULL, model TEXT NOT NULL, payload TEXT NOT NULL,
        UNIQUE(frame,cutoff,model));
        CREATE INDEX IF NOT EXISTS diag_decisions_at ON diagnostic_decisions(at,model);
        CREATE TABLE IF NOT EXISTS diagnostic_sessions (id TEXT PRIMARY KEY, first_at REAL NOT NULL,last_at REAL NOT NULL);''')
        db.execute("INSERT OR IGNORE INTO meta VALUES ('diagnostic_instance',?)",(uuid.uuid4().hex,))
        self.journal_instance=db.execute("SELECT value FROM meta WHERE key='diagnostic_instance'").fetchone()[0]

    def sample(self,db,frame,now,status,snapshot=None):
        q=snapshot['quote'] if snapshot else None
        payload={'frame':frame,'observed_at':now,'observed_at_utc':utc(now),'status':status,'source':SOURCE,
                 'session_id':self.session_id,'engine_version':VERSION,'model_sha256':self.model_sha256,
                 'closed_candle_close_utc':utc(snapshot['bars'][-1][0]+STEPS[frame]) if snapshot else None,
                 'quote_time_utc':utc(q['time']) if q else None,'bid_ask_age_seconds':now-q['time'] if q else None}
        db.execute('INSERT INTO diagnostic_samples(frame,at,status,session,payload) VALUES (?,?,?,?,?)',
                   (frame,now,status,self.session_id,json.dumps(payload,allow_nan=False)))
        db.execute('INSERT INTO diagnostic_sessions VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET last_at=excluded.last_at',(self.session_id,now,now))
        db.execute("INSERT OR IGNORE INTO meta VALUES ('diagnostic_first_at',?)",(str(now),))
        if self._diagnostic_pruned_at is None or now-self._diagnostic_pruned_at>=60 or now<self._diagnostic_pruned_at:
            pruned=0
            for table,cap in [('diagnostic_samples',200000),('diagnostic_decisions',100000)]:
                pruned+=db.execute(f'DELETE FROM {table} WHERE at<?',(now-49*3600,)).rowcount
                pruned+=db.execute(f'DELETE FROM {table} WHERE seq IN (SELECT seq FROM {table} ORDER BY seq DESC LIMIT -1 OFFSET ?)',(cap,)).rowcount
            if pruned:
                db.execute("INSERT INTO meta VALUES ('diagnostic_pruned',?) ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+excluded.value",(pruned,))
            db.execute('DELETE FROM diagnostic_sessions WHERE last_at<?',(now-49*3600,))
            self._diagnostic_pruned_at=now

    def record_frame_failure(self,frame,now,code):
        allowed={'STALE_CANDLES','QUOTE_GAP','CANDLE_GAP','SOURCE_MISMATCH','PUBLIC_FRAME_UNAVAILABLE','OBSERVER_PROCESSING_FAILED'}
        if frame not in STEPS or code not in allowed:raise ValueError('INVALID_FRAME_DIAGNOSTIC')
        with self.connection() as db:self.sample(db,frame,now,code)

    def diagnostics(self,now,hours=24):
        if hours not in (24,48) or type(hours) is not int:raise ValueError('INVALID_DIAGNOSTIC_WINDOW')
        since=now-hours*3600
        with self.connection() as db:
            decisions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM diagnostic_decisions WHERE at>=? AND at<=? AND model=? ORDER BY at,seq',(since,now,self.model_sha256))]
            samples=list(db.execute('SELECT frame,at,status FROM diagnostic_samples WHERE at>=? AND at<=? ORDER BY frame,at,seq',(since,now)))
            meta={r['key']:r['value'] for r in db.execute("SELECT * FROM meta WHERE key IN ('diagnostic_first_at','diagnostic_pruned')")}
            sessions=db.execute('SELECT COUNT(*) FROM diagnostic_sessions WHERE last_at>=? AND first_at<=?',(since,now)).fetchone()[0]
        coverage={}
        for frame in STEPS:
            xs=[r for r in samples if r['frame']==frame];gaps=[b['at']-a['at'] for a,b in zip(xs,xs[1:])]
            counts=Counter(r['status'] for r in xs)
            coverage[frame]={'samples':len(xs),'successful_samples':counts['LIVE'],'status_counts':dict(counts),
                'first_sample_utc':utc(xs[0]['at']) if xs else None,'last_sample_utc':utc(xs[-1]['at']) if xs else None,
                'sample_span_seconds':xs[-1]['at']-xs[0]['at'] if xs else 0,'maximum_sample_gap_seconds':max(gaps,default=None),
                'cadence_observed_seconds':sum(g for g in gaps if 0<=g<=15),
                'unobserved_gap_seconds':sum(g for g in gaps if g>15),'window_seconds':hours*3600,
                'continuous_hosting_verified':False,'coverage_complete':False}
        groups=[]
        for frame in STEPS:
            failures=coverage[frame]['status_counts']
            for family in FAMILIES:
                for side in ('LONG','SHORT'):
                    rows=[x for batch in decisions for x in batch if (x['frame'],x['strategy'],x['direction'])==(frame,family,side)]
                    reasons=Counter(code for r in rows for code in r['reason_codes'])
                    groups.append({'frame':frame,'strategy':family,'direction':side,'variant':'BASE',
                        'candles_evaluated':len(rows),'candidates':sum(r['candidate'] is True for r in rows),
                        'WATCH':sum(r['state']=='WATCH' for r in rows),'triggered_WATCH':sum(r['state']=='WATCH' and r['technical_trigger'] for r in rows),
                        'REJECTED':sum(r['state']=='REJECTED' for r in rows),'NO_TRADE':sum(r['state']=='NO TRADE' for r in rows),
                        'CONFIRMED':sum(r['state']=='CONFIRMED' for r in rows),'trace_mismatches':sum(r['trace_integrity']!='OK' for r in rows),
                        'reason_codes':dict(sorted(reasons.items())),'stale_samples':failures.get('STALE_CANDLES',0),
                        'quote_gaps':failures.get('QUOTE_GAP',0),'candle_gaps':failures.get('CANDLE_GAP',0),
                        'offline_samples':failures.get('PUBLIC_FRAME_UNAVAILABLE',0),
                        'processing_failures':failures.get('OBSERVER_PROCESSING_FAILED',0),'delivered_alerts':None,'acknowledged_alerts':None})
        return {'scope':'AURA5_SIGNAL_DIAGNOSTICS','hours':hours,'window_start_utc':utc(since),'window_end_utc':utc(now),
                'server_time':now,'source':SOURCE,'engine_version':VERSION,'model_sha256':self.model_sha256,
                'diagnostics_version':DIAGNOSTICS_VERSION,'journal_instance':self.journal_instance,'writer_session':self.session_id,
                'first_recorded_observation_utc':utc(float(meta['diagnostic_first_at'])) if 'diagnostic_first_at' in meta else None,
                'writer_sessions_in_window':sessions,'pruned_rows':int(meta.get('diagnostic_pruned',0)),
                'history_before_instance':'UNKNOWN_OR_LOST','coverage':coverage,'groups':groups,
                'unique_frame_candles_evaluated':len(decisions),'recent_decisions':[x for batch in decisions[-16:] for x in batch],
                'alert_delivery_scope':'THIS_BROWSER_ONLY; SERVER_DOES_NOT_RECEIVE_ACKS',
                'continuous_hosting_verified':False,'execution_enabled':False,'account_connected':False}

    def export_diagnostics(self,now,hours=24,kind='decisions',after=0,limit=500):
        if hours not in (24,48) or type(hours) is not int or kind not in ('decisions','samples') or type(after) is not int or after<0 or type(limit) is not int or not 1<=limit<=1000:
            raise ValueError('INVALID_DIAGNOSTIC_PAGE')
        table={'decisions':'diagnostic_decisions','samples':'diagnostic_samples'}[kind]
        with self.connection() as db:
            rows=db.execute(f'SELECT seq,payload FROM {table} WHERE at>=? AND at<=? AND seq>? ORDER BY seq LIMIT ?', (now-hours*3600,now,after,limit+1)).fetchall()
        items=[{'seq':r['seq'],'data':json.loads(r['payload'])} for r in rows[:limit]]
        return {'scope':'AURA5_ANONYMIZED_SIGNAL_JOURNAL','journal_instance':self.journal_instance,'kind':kind,'hours':hours,
                'items':items,'has_more':len(rows)>limit,'next_after':items[-1]['seq'] if items else after,
                'includes_private_account_data':False,'history_before_instance':'UNKNOWN_OR_LOST'}

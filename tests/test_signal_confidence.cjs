'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {usable,validThreshold,reserveAudio,manualCosts,LocalJournal,VERSION}=require('../static/signal-confidence.js');
const SOURCE='BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2';
function payload(){const now=600601,q={bid:49999.9,ask:50000.1,time:now,received_at:now,source:SOURCE};
 const c={id:'a'.repeat(64),score:80,score_groups:{trend:30,momentum:25,structure:10,volume:0,support_resistance:15},
  score_version:VERSION,model_sha256:'b'.repeat(64),score_model_sha256:'d'.repeat(64),input_sha256:'c'.repeat(64),direction:'LONG',frame:'5m',source:SOURCE,
  statistical_status:'UNVALIDATED',probability_tp_before_sl:null,exchange_execution:false,manual_only:true,
  closed_at:600600,valid_until:600900,quote_time:now,quote_received_at:now,
  bid:q.bid,ask:q.ask,
  entry:50000.1,sl:49850,tp:50300,net_rr:1.8,risk_gates_passed:true,state:'WATCH_RESEARCH',
  costs:{cost_version:'AURA5_EXIT_QUOTE_COSTS_2',entry_basis:'EXECUTABLE_QUOTE'}};
 const d={scope:'AURA6_PUBLIC_OBSERVER_ONLY',execution_enabled:false,account_connected:false,
  observer:{running:true},confidence_version:VERSION,model_sha256:c.model_sha256,
  server_time:now,fresh_frames:['5m'],quotes:{'5m':q},confidence_candidates:[c]};
 return {now,c,d};}
test('threshold, labels are technical not probabilities',()=>{
 const {now,c,d}=payload();assert.equal(usable(d,c,now,50),true);assert.equal(usable(d,c,now,80),true);
 assert.equal(usable(d,c,now,81),false);assert.equal(validThreshold(49),false);assert.equal(validThreshold(100),true);
 assert.equal(usable(d,{...c,probability_tp_before_sl:.8},now),false);
});
test('manual RR exactly matches Python fee, slip, funding and exit-quote costs',()=>{
 const {c}=payload();const x=manualCosts(c,[50000.1,49850,50300]);
 assert.ok(Math.abs(x.net_rr-0.4738003397564491)<1e-12);
 assert.ok(Math.abs(x.net_loss-304.8752350499892)<1e-9);
 assert.ok(Math.abs(x.funding_reserve-5.00001)<1e-9);
 const y=manualCosts({...c,direction:'SHORT',frame:'15m'},[50000,50200,49500]);
 assert.ok(Math.abs(y.net_rr-0.9731217356820372)<1e-12);
 assert.equal(manualCosts({...c,costs:{cost_version:'UNKNOWN'}},[50000,49850,50300]),null);
 assert.equal(manualCosts(c,[50000,51000,52000]),null);
 assert.ok(manualCosts(c,[50000.1,49700,51000]).net_rr>=1.5);
});
for(const [name,change]of Object.entries({
 oldQuote:({d})=>{d.quotes['5m'].time-=6;},
 staleServer:({d})=>{d.server_time-=11;},
 stopped:({d})=>{d.observer.running=false;},
 modelMismatch:({d})=>{d.model_sha256='f'.repeat(64);},
 riskFailed:({c})=>{c.risk_gates_passed=false;},
 invalidRR:({c})=>{c.net_rr=1.4;},
 falseConfirmed:({c})=>{c.statistical_status='VALIDATED';},
 badScore:({c})=>{c.score=99;},
 badSource:({d})=>{d.quotes['5m'].source='BYBIT';},
 crossed:({c})=>{c.sl=50100;},
 readonlyViolation:({d})=>{d.execution_enabled=true;},
})){test('confidence fails closed: '+name,()=>{const a=payload();change(a);assert.equal(usable(a.d,a.c,a.now),false);});}
test('local score journal persists threshold, copy, manual edits and UNKNOWN gaps',()=>{
 const map=new Map(),storage={getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v)};
 const j=new LocalJournal(storage),{c,now}=payload();assert.equal(j.threshold,50);j.threshold=73;j.save();
 assert.equal(j.seen(c,now),true);assert.equal(j.seen(c,now),false);
 assert.equal(j.copied(c,now+1),true);assert.equal(j.edited(c.id,[50001,49800,50300],now+2),true);
 const reloaded=new LocalJournal(storage);assert.equal(reloaded.threshold,73);
 assert.equal(reloaded.rows.length,1);assert.equal(reloaded.rows[0].outcome,'UNKNOWN');
  assert.equal(reloaded.rows[0].manual_adjustments.length,1);
  const outcome={id:c.id,score:c.score,score_version:VERSION,
    score_model_sha256:c.score_model_sha256,input_sha256:c.input_sha256,quote_time:c.quote_time,
    outcome:'UNKNOWN',result:{note:'RECOVERY_CANDLE_GAP'}};
  assert.equal(reloaded.outcomes([{...outcome,quote_time:c.quote_time+1,outcome:'TP'}]),false);
  assert.equal(reloaded.outcomes([{...outcome,input_sha256:'e'.repeat(64),outcome:'TP'}]),false);
  assert.equal(reloaded.outcomes([outcome]),true);
  assert.equal(reloaded.rows[0].outcome,'UNKNOWN');assert.equal(reloaded.rows[0].gap,'RECOVERY_CANDLE_GAP');
  const changed={...c,quote_time:c.quote_time+1,entry:50003,sl:49800,tp:50500};
  assert.equal(reloaded.copied(changed,now+4),true);
  assert.equal(reloaded.rows[0].quote_time,changed.quote_time);
  assert.equal(reloaded.rows[0].entry,50003);
  assert.equal(reloaded.rows[0].outcome,'UNKNOWN');
  assert.equal(reloaded.outcomes([{...outcome,outcome:'TP'}]),false);
  assert.equal(reserveAudio(storage,c.id),true);
  assert.equal(reserveAudio(storage,c.id),false);
  assert.equal(reserveAudio(storage,'bad'),false);
});

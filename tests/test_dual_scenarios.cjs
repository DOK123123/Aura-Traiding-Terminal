'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {displaySides}=require('../static/signal-confidence.js');
test('missing and disconnected data keeps all eight sides UNKNOWN without levels',()=>{
 for(const data of [null,{}, {observer:{running:false},server_time:100}]){
  const rows=displaySides(data,100);
  assert.equal(rows.length,8);
  assert.deepEqual(rows.map(x=>x.direction),['LONG','SHORT','LONG','SHORT','LONG','SHORT','LONG','SHORT']);
  for(const x of rows){assert.equal(x.state,'UNKNOWN');assert.equal(x.score,null);assert.equal(x.entry,undefined);}
 }
});

function fixture(){
 const now=600601,source='BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2';
 const q={source,bid:49999.9,ask:50000.1,time:now,received_at:now};
 const c={id:'a'.repeat(64),direction:'LONG',frame:'5m',score:80,
  score_groups:{trend:30,momentum:25,structure:10,volume:0,support_resistance:15},
  score_version:'AURA5_TECHNICAL_SCORE_V1_FROZEN',score_model_sha256:'d'.repeat(64),
  model_sha256:'b'.repeat(64),source,statistical_status:'UNVALIDATED',probability_tp_before_sl:null,
  manual_only:true,exchange_execution:false,state:'WATCH_RESEARCH',technical_trigger:true,
  closed_at:600600,valid_until:600900,quote_time:now,quote_received_at:now,bid:q.bid,ask:q.ask,
  entry:q.ask,sl:49700,tp:51000,net_rr:2.2,risk_gates_passed:true};
 const short={...c,id:'e'.repeat(64),direction:'SHORT',score:40,
  state:'REJECTED',risk_gates_passed:false,technical_trigger:false,
  entry:null,sl:null,tp:null,net_rr:null,rejection_reasons:['RSI_EXTREME']};
 const d={scope:'AURA6_PUBLIC_OBSERVER_ONLY',execution_enabled:false,account_connected:false,
  observer:{running:true},confidence_version:c.score_version,model_sha256:c.model_sha256,
  server_time:now,fresh_frames:['5m'],quotes:{'5m':q},confidence_candidates:[c,short],dual_scenarios:[c,short]};
 return {now,c,d};
}
test('both sides remain visible independently of score threshold',()=>{
 const {d,now}=fixture();
 const [long,short]=displaySides(d,now);
 assert.equal(long.state,'WATCH');assert.equal(long.score,80);
 assert.equal(short.state,'REJECTED');assert.equal(short.score,40);
 assert.deepEqual(short.rejection_reasons.slice(0,1),['RSI_EXTREME']);
 const higher=displaySides(d,now,81);
 assert.equal(higher.length,8);assert.equal(higher[0].state,'REJECTED');assert.equal(higher[0].score,80);
 assert.equal(higher[1].score,40);
});
test('stale, stopped, foreign, future and expired inputs clear scores for both sides',()=>{
 for(const change of [
  d=>{d.quotes['5m'].time-=6;},d=>{d.observer.running=false;},
  d=>{d.quotes['5m'].source='BYBIT';},d=>{d.server_time-=11;},
  d=>{d.quotes['5m'].received_at+=1;},d=>{d.execution_enabled=true;},
  d=>{for(const c of d.dual_scenarios)c.valid_until=600600;},
 ]){
  const {d,now}=fixture();change(d);
  for(const row of displaySides(d,now)){assert.equal(row.state,'UNKNOWN');assert.equal(row.score,null);assert.equal(row.entry,undefined);}
 }
});

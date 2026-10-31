'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {homeState,resolveTab}=require('../static/aura-mobile-shell.js');
const SOURCE='BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2';
const now=1700000000;
function sample(){return {scope:'AURA6_PUBLIC_OBSERVER_ONLY',server_time:now,
  execution_enabled:false,account_connected:false,observer:{running:true},fresh_frames:['5m'],
  quotes:{'5m':{source:SOURCE,bid:49990,ask:50000,time:now,received_at:now}},
  confidence_candidates:[{direction:'LONG',score:75,entry:50000,sl:49000,tp:53000,net_rr:2}]};}

test('only the four supported tabs are routable; no script or other hash injects tab',()=>{
  for(const tab of ['home','signals','chart','more'])assert.equal(resolveTab('#app-'+tab),tab);
  for(const hash of ['#app-active43','#aura-live-analyst','#app-signals/foo','#APP-home','<script>'])assert.equal(resolveTab(hash),'home');
});
test('home never confuses technical score with validated edge',()=>{
  const d=sample();let checked=0;
  const result=homeState(d,now,50,(_,c,t,threshold)=>{checked++;return c.score>=threshold;});
  assert.equal(result.state,'WATCH');assert.equal(result.candidate.direction,'LONG');
  assert.equal(result.quote.ask,50000);assert.equal(checked,1);
  assert.equal(homeState(d,now,80,(_,c,t,threshold)=>c.score>=threshold).state,'WAIT');
});
test('no fabricated LIVE or signals when observer, server, quote or account integrity fails',()=>{
  const changes=[d=>d.observer.running=false,d=>d.execution_enabled=true,d=>d.account_connected=true,
    d=>d.scope='HISTORY_ONLY',d=>d.server_time=now-11,d=>d.fresh_frames=[],
    d=>d.quotes['5m'].time=now-6,d=>d.quotes['5m'].received_at=now-6,
    d=>d.quotes['5m'].time=now+1,d=>d.quotes['5m'].bid=0,
    d=>d.quotes['5m'].ask=d.quotes['5m'].bid-1,d=>d.quotes['5m'].source='HISTORICAL',
    d=>d.quotes['5m'].ask=60000];
  for(const change of changes){const d=sample();change(d);const r=homeState(d,now,50,()=>true);
    assert.equal(r.state,'STALE');assert.equal(r.quote,null);}
  assert.equal(homeState(null,now,50,()=>true).state,'STALE');
  assert.equal(homeState(sample(),now,50,()=>false).state,'WAIT');
});
test('defensive fallback for malformed confidence threshold and absent scorer',()=>{
  const d=sample();
  assert.equal(homeState(d,now,-1,(_,c,t,threshold)=>threshold===50).state,'WATCH');
  assert.equal(homeState(d,now,50,undefined).state,'WAIT');
  d.confidence_candidates={bad:true};assert.equal(homeState(d,now,50,()=>true).state,'WAIT');
});

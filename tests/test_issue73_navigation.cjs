'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {homeState,resolveTab,HomeFeed}=require('../static/aura-mobile-shell.js');
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

const flush=()=>new Promise(resolve=>setImmediate(resolve));
function monitor(){
  let at=now,serial=0;const intervals=new Map(),timeouts=new Map(),requests=[],seen=[];
  const timers={setInterval(fn,ms){const id=++serial;intervals.set(id,{fn,ms});return id;},
    clearInterval(id){intervals.delete(id);},setTimeout(fn,ms){const id=++serial;timeouts.set(id,{fn,ms});return id;},
    clearTimeout(id){timeouts.delete(id);}};
  const feed=new HomeFeed({timers,clock:()=>at,onData:(data,time)=>seen.push(homeState(data,time,50,()=>true)),
    fetcher:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
  return {feed,requests,seen,intervals,timeouts,at:value=>at=value,
    tick:ms=>{for(const value of [...intervals.values()])if(value.ms===ms)value.fn();},
    timeout:()=>{for(const value of [...timeouts.values()])value.fn();}};
}
const reply=data=>({ok:true,json:async()=>data});
test('pending network cannot keep expired Bid/Ask and WATCH on Home',async()=>{
  const h=monitor();h.feed.start();h.requests[0].resolve(reply(sample()));await flush();
  assert.equal(h.seen.at(-1).state,'WATCH');
  h.at(now+4);h.tick(4000);assert.equal(h.requests.length,2);
  h.at(now+6);h.tick(1000);
  assert.equal(h.seen.at(-1).state,'STALE');assert.equal(h.seen.at(-1).quote,null);
  assert.equal(h.requests[1].options.method,undefined);
  assert.equal(h.requests[1].url,'/api/preview/signals/snapshot');h.feed.stop();
});
test('one bounded request; timeout aborts, late response cannot replace recovery',async()=>{
  const h=monitor();h.feed.start();h.tick(4000);h.tick(4000);
  assert.equal(h.requests.length,1);assert.equal([...h.timeouts.values()][0].ms,8000);
  h.timeout();assert.equal(h.requests[0].options.signal.aborted,true);
  assert.equal(h.seen.at(-1).state,'STALE');
  h.tick(4000);h.requests[1].resolve(reply(sample()));await flush();
  assert.equal(h.seen.at(-1).state,'WATCH');
  h.requests[0].resolve(reply(null));await flush();
  assert.equal(h.seen.at(-1).state,'WATCH');h.feed.stop();
});
test('suspend and resume are idempotent; stopped requests cannot repaint a new session',async()=>{
  const h=monitor();h.feed.start();h.feed.start();assert.equal(h.requests.length,1);
  h.feed.stop();assert.equal(h.requests[0].options.signal.aborted,true);
  assert.equal(h.intervals.size,0);assert.equal(h.timeouts.size,0);
  h.feed.start();h.requests[1].resolve(reply(sample()));await flush();
  h.requests[0].reject(Error('old request failed'));await flush();
  assert.equal(h.seen.at(-1).state,'WATCH');assert.equal(h.intervals.size,2);
  h.feed.stop();assert.equal(h.seen.at(-1).state,'STALE');
});
test('HTTP and JSON errors clear cached LIVE; a fresh response restores it',async()=>{
  for(const bad of [{ok:false},{ok:true,json:async()=>{throw Error('invalid JSON');}}]){
    const h=monitor();h.feed.start();h.requests[0].resolve(reply(sample()));await flush();
    h.tick(4000);h.requests[1].resolve(bad);await flush();assert.equal(h.seen.at(-1).state,'STALE');
    h.tick(4000);h.requests[2].resolve(reply(sample()));await flush();assert.equal(h.seen.at(-1).state,'WATCH');h.feed.stop();
  }
});
test('invalid browser clock never labels a snapshot LIVE',()=>{
  for(const at of [NaN,Infinity,-Infinity])assert.equal(homeState(sample(),at,50,()=>true).state,'STALE');
});


// Offline account-panel tests; no browser, credentials, exchange or orders.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function environment(first) {
  let now=1800000000000, answer=first;
  const elements=new Map(), requests=[], timers=new Map(), intervals=new Map(), events=new Map();
  let id=0;
  class Element {
    constructor() {this.textContent='';this.hidden=false;this.disabled=false;this.children=[];this.events={};}
    append(child) {this.children.push(child);}
    replaceChildren() {this.children=[];}
    addEventListener(name,fn) {this.events[name]=fn;}
  }
  const el=name=>{
    if(!elements.has(name))elements.set(name,new Element());
    return elements.get(name);
  };
  el('data').hidden=el('history').hidden=el('login').hidden=true;
  el('history-symbol').value='BTCUSDT';
  class Clock extends Date {static now(){return now;}}
  const connected=()=>({status:'Connected',testnet:true,read_only:true,stale:false,cache_age_seconds:0,
    checked_at:new Date(now).toISOString(),balances:[{asset:'USDT',free:'10000.12345678',locked:'0.00000001',total:'10000.12345679'}],
    available_assets:['USDT'],open_orders:[]});
  const response=data=>({ok:true,status:200,json:async()=>data});
  const sandbox={Date:Clock,AbortController,Math,Number,String,
    document:{hidden:false,getElementById:key=>el(key.replace('testnet-','')),createElement:()=>new Element(),
      addEventListener:(name,fn)=>events.set(name,fn)},
    window:{addEventListener:(name,fn)=>events.set(name,fn)},location:{reload(){}},
    setTimeout:fn=>{timers.set(++id,fn);return id;},clearTimeout:key=>timers.delete(key),
    setInterval:fn=>{intervals.set(++id,fn);return id;},clearInterval:key=>intervals.delete(key),
    fetch:async(url,options)=>{requests.push({url,options}); return typeof answer==='function'?await answer(url,options):answer;}};
  const context=vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/testnet.js'),'utf8'),context);
  const flush=async()=>{for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));};
  return {el,requests,connected,response,timers,events,intervals,flush,
    set:data=>{answer=data;},click:name=>el(name).events.click(),
    tick:ms=>{now+=ms;for(const fn of intervals.values())fn();},
    hide:value=>{sandbox.document.hidden=value;events.get('visibilitychange')();}};
}

const reply=data=>({status:200,ok:true,json:async()=>data});

test('missing config keeps account hidden and fetches only own GET endpoint',async()=>{
  const e=environment(reply({status:'Not configured',message:'Настройте Render.'}));await e.flush();
  assert.equal(e.el('state').textContent,'Not configured');assert.equal(e.el('data').hidden,true);
  assert.equal(e.requests.length,1);assert.equal(e.requests[0].url,'/api/testnet/account');
  const opts=e.requests[0].options;
  assert.equal(opts.method,'GET');assert.equal(opts.cache,'no-store');assert.equal(opts.credentials,'same-origin');
  assert.equal(opts.headers,undefined);
});
test('owner login required clears data and shows safe login link',async()=>{
  const e=environment({status:401,ok:false});await e.flush();
  assert.equal(e.el('state').textContent,'Disconnected');assert.equal(e.el('login').hidden,false);
  assert.equal(e.el('data').hidden,true);assert.match(e.el('message').textContent,/aura/);
});
test('fail closed when owner password absent',async()=>{
  const e=environment({status:403,ok:false});await e.flush();
  assert.equal(e.el('state').textContent,'Disconnected');assert.equal(e.el('login').hidden,true);
  assert.match(e.el('message').textContent,/AURA_TESTNET_VIEW_PASSWORD/);
});
test('balance amounts retain precision and empty orders are explicit',async()=>{
  const e=environment(reply({status:'Not configured'}));await e.flush();
  e.set(e.response(e.connected()));e.click('refresh');await e.flush();
  assert.equal(e.el('state').textContent,'Connected');assert.equal(e.el('data').hidden,false);
  assert.equal(e.el('balances').children[0].children[1].textContent,'10000.12345678');
  assert.equal(e.el('balances').children[0].children[3].textContent,'10000.12345679');
  assert.match(e.el('orders').children[0].children[0].textContent,/Нет открытых/);
});
test('upstream failure removes former balances and automatically recovers',async()=>{
  const e=environment(reply({status:'Not configured'}));await e.flush();
  e.set(e.response(e.connected()));e.click('refresh');await e.flush();
  e.set(e.response({status:'Disconnected',stale:true,message:'Timeout',retry_after:30}));e.tick(60001);await e.flush();
  assert.equal(e.el('state').textContent,'Disconnected');assert.equal(e.el('balances').children.length,0);
  e.set(e.response(e.connected()));e.tick(60001);await e.flush();assert.equal(e.el('state').textContent,'Connected');
});
test('rate-limit cooldown suppresses automatic polls',async()=>{
  const e=environment(reply({status:'Disconnected',stale:true,message:'Rate limit',retry_after:120}));await e.flush();
  e.tick(60000);await e.flush();assert.equal(e.requests.length,1);
  e.tick(60001);await e.flush();assert.equal(e.requests.length,2);
});
test('stale and hidden-tab snapshots never keep balances visible',async()=>{
  const e=environment(reply({status:'Not configured'}));await e.flush();
  e.set(e.response(e.connected()));e.click('refresh');await e.flush();
  e.hide(true);e.tick(91000);await e.flush();
  assert.equal(e.el('state').textContent,'Disconnected');assert.equal(e.el('data').hidden,true);
  assert.match(e.el('message').textContent,/устарели/);
});
test('account history is read on demand and rendered as text',async()=>{
  const e=environment(reply({status:'Not configured'}));await e.flush();
  e.set(e.response(e.connected()));e.click('refresh');await e.flush();
  assert.ok(!e.requests.some(r=>r.url.startsWith('/api/testnet/history')));
  e.set(e.response({status:'Connected',stale:false,checked_at:'2026-10-11T12:00:00Z',
    orders:[],trades:[],message:'BTCUSDT · последние 100'}));e.click('history-refresh');await e.flush();
  assert.equal(e.requests.at(-1).url,'/api/testnet/history?symbol=BTCUSDT');assert.equal(e.el('history').hidden,false);
  assert.match(e.el('history-status').textContent,/BTCUSDT/);
});
test('pending history is discarded when account becomes disconnected',async()=>{
  const e=environment(reply({status:'Not configured'}));await e.flush();
  e.set(e.response(e.connected()));e.click('refresh');await e.flush();
  let release;
  e.set(url=>url.startsWith('/api/testnet/history')?new Promise(resolve=>{release=resolve;}):e.response({status:'Disconnected',message:'offline'}));
  e.click('history-refresh');await e.flush();e.click('refresh');await e.flush();
  release(e.response({status:'Connected',orders:[],trades:[],checked_at:'2026-10-11T12:00:00Z',message:'old'}));await e.flush();
  assert.equal(e.el('history').hidden,true);assert.equal(e.el('past-orders').children.length,0);
});
test('page exit aborts reads and polling',async()=>{
  const e=environment(reply({status:'Not configured'}));await e.flush();
  e.events.get('pagehide')();assert.equal(e.intervals.size,0);
  const count=e.requests.length;e.click('refresh');await e.flush();assert.equal(e.requests.length,count);
});

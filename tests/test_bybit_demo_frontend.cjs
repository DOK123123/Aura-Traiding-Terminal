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
  el('symbol').value='BTCUSDT'; el('category').value='spot';
  class Clock extends Date {static now(){return now;}}
  const identity=()=>({provider:'BYBIT_DEMO',demo:true,read_only:true,virtual_funds:true,real_money:false,
    symbol:el('symbol').value,category:el('category').value});
  const connected=()=>({...identity(),status:'Connected',stale:false,cache_age_seconds:0,
    checked_at:new Date(now).toISOString(),demo_balance:{wallet_balance_usd:'10000.12345678',equity_usd:'9999',available_balance_usd:null},
    balances:[{asset:'USDT',wallet_balance:'10000.12345678',equity:'9999',locked:null,usd_value:'9999',spot_borrow:'1'}],
    available_assets:['USDT'],open_orders:[],open_orders_scope:el('category').value.toUpperCase()+' / '+el('symbol').value});
  const response=data=>({ok:true,status:200,json:async()=>data});
  const sandbox={Date:Clock,AbortController,Math,Number,String,
    document:{hidden:false,getElementById:key=>el(key.replace('demo-','')),createElement:()=>new Element(),
      addEventListener:(name,fn)=>events.set(name,fn)},
    window:{addEventListener:(name,fn)=>events.set(name,fn)},location:{reload(){}},
    setTimeout:fn=>{timers.set(++id,fn);return id;},clearTimeout:key=>timers.delete(key),
    setInterval:fn=>{intervals.set(++id,fn);return id;},clearInterval:key=>intervals.delete(key),
    fetch:async(url,options)=>{requests.push({url,options}); return typeof answer==='function'?await answer(url,options):answer;}};
  const context=vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/bybit_demo.js'),'utf8'),context);
  const flush=async()=>{for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));};
  return {el,requests,connected,identity,response,timers,events,intervals,flush,
    set:data=>{answer=data;},click:name=>el(name).events.click(),
    change:(name,value)=>{el(name).value=value;el(name).events.change();},
    tick:ms=>{now+=ms;for(const fn of intervals.values())fn();},
    hide:value=>{sandbox.document.hidden=value;events.get('visibilitychange')();}};
}

const reply=data=>({status:200,ok:true,json:async()=>data});
test('not configured keeps market account UI safe and only fetches own Demo GET route',async()=>{
 const e=environment(reply({status:'Not configured',message:'Configure Demo ENV'}));await e.flush();
 assert.equal(e.el('state').textContent,'Not configured');assert.equal(e.el('data').hidden,true);
 assert.equal(e.requests[0].url,'/api/bybit-demo/account?category=spot&symbol=BTCUSDT');
 const opts=e.requests[0].options;
 assert.equal(opts.method,'GET');assert.equal(opts.cache,'no-store');assert.equal(opts.credentials,'same-origin');
 assert.equal(opts.headers,undefined);
});
test('owner login and absent owner password fail closed',async()=>{
 const e=environment({status:401,ok:false});await e.flush();
 assert.equal(e.el('login').hidden,false);assert.equal(e.el('data').hidden,true);assert.match(e.el('message').textContent,/aura/);
 e.set({status:403,ok:false});e.click('refresh');await e.flush();
 assert.equal(e.el('login').hidden,true);assert.match(e.el('message').textContent,/AURA_TESTNET_VIEW_PASSWORD/);
});
test('Demo balances preserve decimal text and absent amounts are not invented zeros',async()=>{
 const e=environment(reply({status:'Not configured'}));await e.flush();
 e.set(e.response(e.connected()));e.click('refresh');await e.flush();
 assert.equal(e.el('state').textContent,'Connected');assert.equal(e.el('data').hidden,false);
 assert.equal(e.el('balances').children[0].children[1].textContent,'10000.12345678');
 assert.equal(e.el('balances').children[0].children[3].textContent,'—');
 assert.match(e.el('summary').textContent,/Available margin \(USD\): —/);
 assert.match(e.el('message').textContent,/REAL MONEY IS NOT USED/);
 assert.match(e.el('orders-title').textContent,/SPOT \/ BTCUSDT/);
});
test('upstream rate limit clears balance and respects cooldown',async()=>{
 const e=environment(reply({status:'Not configured'}));await e.flush();
 e.set(e.response(e.connected()));e.click('refresh');await e.flush();
 e.set(reply({status:'Disconnected',stale:true,code:'RATE_LIMITED',message:'Cooldown',retry_after:600}));
 e.tick(60001);await e.flush();assert.equal(e.el('data').hidden,true);
 const count=e.requests.length;e.tick(300000);await e.flush();assert.equal(e.requests.length,count);
 e.set(e.response(e.connected()));e.tick(300001);await e.flush();assert.equal(e.el('state').textContent,'Connected');
});
test('HTTP and network failures never leave former balances visible',async()=>{
 const e=environment(reply({status:'Not configured'}));await e.flush();
 e.set(e.response(e.connected()));e.click('refresh');await e.flush();
 e.set(async()=>{throw new Error('offline')});e.tick(60001);await e.flush();
 assert.equal(e.el('state').textContent,'Disconnected');assert.equal(e.el('balances').children.length,0);
 e.set(reply({status:'Disconnected',message:'HTTP 403: region/IP or rate limit',retry_after:600}));
 e.click('refresh');await e.flush();assert.match(e.el('message').textContent,/403/);
});
test('stale snapshots expire while hidden and recover after return',async()=>{
 const e=environment(reply({status:'Not configured'}));await e.flush();
 e.set(e.response(e.connected()));e.click('refresh');await e.flush();
 e.hide(true);e.tick(91000);await e.flush();
 assert.equal(e.el('data').hidden,true);assert.match(e.el('message').textContent,/устарели/);
 e.hide(false);await e.flush();assert.equal(e.el('state').textContent,'Connected');
});
test('foreign provider or mismatched category cannot appear as connected',async()=>{
 for(const patch of [{provider:'BINANCE_TESTNET'},{category:'linear'},{real_money:true},{demo:false},{read_only:false}]){
  const e=environment(reply({status:'Not configured'}));await e.flush();
  e.set(e.response({...e.connected(),...patch}));e.click('refresh');await e.flush();
  assert.equal(e.el('state').textContent,'Disconnected');assert.equal(e.el('data').hidden,true);
 }
});
test('category change cancels stale requests and displays only new scope',async()=>{
 const e=environment(reply({status:'Not configured'}));await e.flush();
 let release;
 e.set(()=>new Promise(resolve=>{release=resolve}));e.click('refresh');await e.flush();
 const old=e.connected();e.set(e.response({...old,category:'linear',open_orders_scope:'LINEAR / BTCUSDT'}));
 e.change('category','linear');assert.equal(e.requests.at(-1).options.signal.aborted,true);
 release(e.response(old));await e.flush();
 assert.equal(e.requests.at(-1).url,'/api/bybit-demo/account?category=linear&symbol=BTCUSDT');
 assert.equal(e.el('state').textContent,'Connected');assert.match(e.el('orders-title').textContent,/LINEAR/);
});
test('history is read on demand, scoped and reports pagination limits',async()=>{
 const e=environment(reply({status:'Not configured'}));await e.flush();
 e.set(e.response(e.connected()));e.click('refresh');await e.flush();
 assert.equal(e.requests.filter(r=>r.url.includes('/history')).length,0);
 e.set(e.response({...e.identity(),status:'Connected',stale:false,checked_at:'2026-10-11T12:00:00Z',
  orders:[],trades:[],orders_has_more:true,trades_has_more:false,message:'Recent 7 days; max 200'}));
 e.click('history-refresh');await e.flush();
 assert.equal(e.requests.at(-1).url,'/api/bybit-demo/history?category=spot&symbol=BTCUSDT');
 assert.equal(e.el('history').hidden,false);assert.match(e.el('history-status').textContent,/СПИСОК ОГРАНИЧЕН/);
});
test('late history is ignored after category change',async()=>{
 const e=environment(reply({status:'Not configured'}));await e.flush();
 e.set(e.response(e.connected()));e.click('refresh');await e.flush();
 let release;
 const old=e.identity();
 e.set(url=>url.includes('/history')?new Promise(resolve=>{release=resolve}):e.response(e.connected()));
 e.click('history-refresh');await e.flush();e.change('category','linear');await e.flush();
 release(e.response({...old,status:'Connected',orders:[],trades:[],stale:false,checked_at:'2026-10-11T12:00:00Z',message:'old'}));await e.flush();
 assert.equal(e.el('history').hidden,true);assert.equal(e.el('past-orders').children.length,0);
});
test('history errors clear account data and do not keep stale connected state',async()=>{
 const e=environment(reply({status:'Not configured'}));await e.flush();
 e.set(e.response(e.connected()));e.click('refresh');await e.flush();
 e.set(reply({status:'Disconnected',message:'Permission denied',retry_after:60}));
 e.click('history-refresh');await e.flush();
 assert.equal(e.el('data').hidden,true);assert.equal(e.el('state').textContent,'Disconnected');
});
test('values render as text and fee rebates are preserved',async()=>{
 const e=environment(reply({status:'Not configured'}));await e.flush();
 e.set(e.response(e.connected()));e.click('refresh');await e.flush();
 e.set(reply({...e.identity(),status:'Connected',stale:false,checked_at:'2026-10-11T12:00:00Z',
  orders:[],trades:[{id:'<img src=x>',order_id:'dummy',side:'Buy',exec_type:'Trade',price:'100',quantity:'1',
   value:'100',fee:'-0.00001',fee_asset:'BTC',time:1700000000000}],message:'Demo'}));
 e.click('history-refresh');await e.flush();
 assert.equal(e.el('trades').children[0].children[0].textContent,'<img src=x>');
 assert.equal(e.el('trades').children[0].children[7].textContent,'-0.00001 BTC');
});
test('page exit aborts requests and polling',async()=>{
 const e=environment(reply({status:'Not configured'}));await e.flush();
 e.events.get('pagehide')();assert.equal(e.intervals.size,0);
 const count=e.requests.length;e.click('refresh');await e.flush();assert.equal(e.requests.length,count);
});

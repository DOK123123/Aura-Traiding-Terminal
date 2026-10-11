// Offline browser-state tests using Node's built-in runner, no browser or network.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function environment() {
  let now = 1800000000000;
  const elements = new Map(), listeners = new Map(), intervals = [], timers = new Map(), sockets = [];
  let timerId=0;
  class Element {
    constructor() { this.textContent=''; this.style={}; this.dataset={}; this.handlers={}; this.value=''; this.checked=true; }
    addEventListener(name,fn) { this.handlers[name]=fn; }
    append() {} replaceChildren() {} checkValidity() { return true; }
  }
  const element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  element('symbol').value='BTCUSDT'; element('limit').value='500';
  for(const [id,value] of Object.entries({lookback:20,matches:100,similarity:75,threshold:60,sample:20,confidence:40,horizons:'5,10,20,50',horizon:20,cost:5,points:50}))element('pattern-'+id).value=String(value);
  class Socket {
    constructor(url) { this.url=url; this.closed=false; sockets.push(this); }
    close() { this.closed=true; }
  }
  class Clock extends Date { static now() {return now;} }
  const series={setData(){},update(){}};
  const context=vm.createContext({Date:Clock,Math,console,Node:Element,AbortController,
    WebSocket:Socket,Event:class{constructor(type){this.type=type;}},CustomEvent:class{constructor(type,props){this.type=type;this.detail=props?.detail;}},
    document:{getElementById:element,addEventListener:(name,fn)=>{if(!listeners.has(name))listeners.set(name,[]);listeners.get(name).push(fn);},
      dispatchEvent:e=>(listeners.get(e.type)||[]).forEach(fn=>fn(e)),createElement:()=>new Element(),querySelectorAll:()=>[],
      querySelector:selector=>selector.startsWith('[data-tf]')?{dataset:{tf:'1m'}}:element(selector)},
    window:{addEventListener(){}},location:{protocol:'https:',host:'aura.example'},
    setInterval:fn=>intervals.push(fn),setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),
    $:element,fmt:String,signed(){},utc:String,chart:{timeScale:()=>({getVisibleLogicalRange:()=>null,getVisibleRange:()=>null,setVisibleLogicalRange(){},setVisibleRange(){}})},
    candles:series,ema20:series,ema50:series,volume:series,requestId:1,currentData:null});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/live.js'),'utf8'),context);
  const snapshot=(source='Binance · Spot')=>({type:'snapshot',symbol:'BTCUSDT',timeframe:'1m',source,mode:'streaming',received_at:now/1000,event_age_seconds:0,
    current_closed:false,last_closed_at:Math.floor(now/60000)*60,stale:false,note:'Live',candles:[{time:Math.floor(now/60000)*60,open:100,high:102,low:99,close:101,volume:5}],
    analysis:{trend:'Bullish',price:101,count:500,signal_up:60,signal_down:40,series:{ema20:[],ema50:[]},factors:{ema:0,rsi:0,momentum:0},damping:1}});
  const run=code=>vm.runInContext(code,context);
  const tick=ms=>{now+=ms;for(const fn of intervals)fn();};
  const deliver=data=>sockets.at(-1).onmessage({data:JSON.stringify(data)});
  const retry=()=>{const pending=[...timers.values()];timers.clear();pending.forEach(fn=>fn());};
  return {context,element,run,tick,deliver,retry,timers,sockets,snapshot};
}

test('closed socket retries once and a fresh snapshot restores signal values',()=>{
  const e=environment(); e.run("startMarketLive(1,'BTCUSDT','1m','500')");e.deliver(e.snapshot());
  const old=e.sockets[0];old.onclose();old.onerror();assert.equal(e.timers.size,1);
  assert.equal(e.element('up').textContent,'—');e.retry();assert.equal(e.sockets.length,2);
  e.deliver(e.snapshot());assert.equal(e.element('up').textContent,'60%');
});
test('silent BTC socket is replaced without waiting for a close event',()=>{
  const e=environment();e.run("startMarketLive(1,'BTCUSDT','1m','500')");e.deliver(e.snapshot());e.tick(31000);
  assert.equal(e.sockets[0].closed,true);assert.equal(e.timers.size,1);assert.equal(e.element('up').textContent,'—');
});
test('slow bootstrap gets two minutes, then retries',()=>{
  const e=environment();e.run("startMarketLive(1,'BTCUSDT','1m','500')");e.tick(60000);
  assert.equal(e.sockets[0].closed,false);e.tick(61000);assert.equal(e.sockets[0].closed,true);
});
test('stale event disables scores before reconnect threshold',()=>{
  const e=environment();e.run("startMarketLive(1,'BTCUSDT','1m','500')");e.deliver(e.snapshot());e.tick(11000);
  assert.equal(e.element('up').textContent,'—');assert.equal(e.sockets[0].closed,false);
});
test('switching market cancels retry and ignores messages from old socket',()=>{
  const e=environment();e.run("startMarketLive(1,'BTCUSDT','1m','500')");const old=e.sockets[0];old.onerror();
  e.run('stopMarketLive(); requestId=2');assert.equal(e.timers.size,0);old.onmessage({data:JSON.stringify(e.snapshot())});
  assert.equal(e.run('currentData'),null);
});
test('status failure hides scores even when previous snapshot is fresh',()=>{
  const e=environment();e.run("startMarketLive(1,'BTCUSDT','1m','500')");e.deliver(e.snapshot());e.deliver({type:'status',message:'upstream offline'});
  assert.equal(e.element('up').textContent,'—');assert.equal(e.element('status').textContent,'upstream offline');
});

async function pattern(e) {
  e.run("startMarketLive(1,'BTCUSDT','1m','500')");e.deliver(e.snapshot());
  const data={status:'OK',mode:'CURRENT MARKET',symbol:'BTCUSDT',timeframe:'1m',source:'Binance · Spot',source_verified:true,signal:'LONG',confidence:80,
    historical_matches:30,average_similarity:90,as_of:1800000000,context:500,archive_bars:5000,archive_first:1799000000,archive_last:1799999940,data_note:'',
    config:{decision_horizon:20},wilson_lower_pct:60,outcomes:{},top_matches:[],explanation:{bullish:[],bearish:[],evidence:[],risks:[]}};
  e.context.fetch=async()=>({ok:true,json:async()=>data});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/patterns.js'),'utf8'),e.context);
  e.element('pattern-run').handlers.click();
  await new Promise(resolve=>setImmediate(resolve));
}
test('source change suppresses a previous directional pattern signal',async()=>{
  const e=environment();await pattern(e);assert.equal(e.element('pattern-signal').textContent,'LONG');
  e.deliver(e.snapshot('TradingView · OANDA:XAUUSD'));assert.equal(e.element('pattern-signal').textContent,'WAIT');
});
test('feed failure suppresses pattern signal and reconnect may restore only matching source',async()=>{
  const e=environment();await pattern(e);e.deliver({type:'status',message:'offline'});
  assert.equal(e.element('pattern-signal').textContent,'WAIT');e.deliver(e.snapshot());assert.equal(e.element('pattern-signal').textContent,'LONG');
});
test('a result arriving during stale BTC data cannot re-enable a directional signal',async()=>{
  const e=environment();await pattern(e);e.tick(11000);
  assert.equal(e.element('pattern-signal').textContent,'WAIT');
  e.run('marketDataChanged()');
  assert.equal(e.element('pattern-signal').textContent,'WAIT');
});

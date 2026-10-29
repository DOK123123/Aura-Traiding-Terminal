const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const A=require('../static/manual-live-analysis.js'),F=require('../static/manual-live-feed.js'),fixture=require('./fixtures/manual_live_synthetic.json');
const snapshot=structuredClone(fixture.snapshots.LONG),now=fixture.now;
function setup(){
 const nodes=new Map(),listeners={},pending=[],created=[];
 class Element{constructor(){this.textContent='';this.style={};this.dataset={};this.handlers={};this.classList={remove(){},toggle(){}};this.options=[{}];this.hidden=false;}addEventListener(n,f){this.handlers[n]=f;}setAttribute(){} }
 const el=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id)};
 const series=()=>({values:[],lines:[],setData(v){this.values=Array.from(v);},applyOptions(){},priceScale(){return{applyOptions(){}}},createPriceLine(opt){const line={...opt,applyOptions(o){Object.assign(this,o)}};this.lines.push(line);return line},removePriceLine(line){this.lines=this.lines.filter(x=>x!==line)}});
 const chart={addSeries(){const s=series();created.push(s);return s;},timeScale(){return{setVisibleLogicalRange(){},fitContent(){}}},subscribeCrosshairMove(){}};
 const document={body:{dataset:{liveManual:'true',manualPreview:'true'}},getElementById:el,querySelectorAll:()=>[],dispatchEvent(){}};
 const window={AuraManualLiveAnalysis:A,AuraManualLiveFeed:F,AuraBitgetLive:{ema:(bars,n)=>bars.slice(n-1).map(b=>({time:b.time,value:b.close}))},LightweightCharts:{createChart:()=>chart,CandlestickSeries:{},LineSeries:{},HistogramSeries:{},CrosshairMode:{Normal:0}},addEventListener:(n,f)=>{(listeners[n]??=[]).push(f)},dispatchEvent(e){for(const f of listeners[e.type]||[])f(e)},AuraManualLiveHub:{status:'RECONNECTING'}};
 class Clock extends Date{static now(){return now*1000}}
 const context=vm.createContext({window,document,Date:Clock,console,AbortController,CustomEvent:class{constructor(type,opt){this.type=type;this.detail=opt?.detail}},fetch:()=>new Promise((resolve,reject)=>pending.push({resolve,reject})),stopMarketLive(){},setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync('static/app.js','utf8'),context);
 const send=s=>window.dispatchEvent({type:'aura-manual-market',detail:s});
 const select=tf=>el('timeframes').handlers.click({target:{closest:()=>({dataset:{tf}})}});
 return {el,window,send,select,created,pending,run:s=>vm.runInContext(s,context)};
}
test('five frames: HISTORY → LIVE → STALE → LIVE preserves authentic OHLCV and independently shows ticker and timestamps',()=>{
 const e=setup(),s=structuredClone(snapshot);s.quote.last=s.quote.bid+.1;s.quote.ask=s.quote.bid+.2;
 const hist={...s,status:'RECONNECTING',quote:null};e.send(hist);assert.match(e.el('feed-state').textContent,/HISTORY ONLY/);
 e.window.AuraManualLiveHub.status='LIVE';e.send(s);
 for(const tf of Object.keys(A.STEPS)){
  e.select(tf);e.send(s);const actual=e.run('currentData');assert.equal(actual.timeframe,tf);
  assert.deepEqual(JSON.parse(JSON.stringify(actual.candles)),s.windows[tf].bars);
  const bar=s.windows[tf].bars.at(-1),metrics=A.metrics(s.windows[tf].bars);
  assert.equal(e.el('headline-price').textContent,Number(s.quote.last).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}));
  assert.equal(e.created[0].lines.length,1);assert.equal(e.created[0].lines[0].price,s.quote.last);assert.equal(e.created[0].values.at(-1).close,bar.close);
  assert.match(e.el('live-candle').textContent,/разница/);assert.match(e.el('live-candle').textContent,/UTC/);assert.match(e.el('event-age').textContent,/Bid .*Ask .*|Bid .* \/ Ask /);assert.match(e.el('event-age').textContent,/UTC/);
  for(const [id,key] of [['rsi','rsi'],['atr','atr'],['ema20-value','ema20'],['ema50-value','ema50']])assert.equal(e.el(id).textContent,Number(metrics[key]).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}));
  assert.equal(e.created[3].values.at(-1).value,bar.volume);
 }
 e.window.AuraManualLiveHub.status='STALE';e.send({status:'STALE',windows:{},quote:null});
 assert.match(e.el('chart-subtitle').textContent,/НЕ LIVE/);assert.equal(e.created[0].lines.length,0);assert.equal(e.created[0].values.length,200);assert.equal(e.el('price').textContent,'—');assert.equal(e.el('rsi').textContent,'—');assert.match(e.el('headline-return').textContent,/НЕ LIVE/);
 e.window.AuraManualLiveHub.status='LIVE';e.send(s);assert.equal(e.el('feed-state').textContent,'LIVE');assert.equal(e.created[0].values.length,201);assert.equal(e.created[0].lines.length,1);
});
test('late failed history response cannot overwrite recovered LIVE display',async()=>{
 const e=setup();e.window.AuraManualLiveHub.status='LIVE';e.send(snapshot);e.pending[0].reject(Error('offline'));await new Promise(r=>setImmediate(r));assert.equal(e.el('feed-state').textContent,'LIVE');assert.match(e.el('status').textContent,/LIVE:/);
});
test('late successful history responses cannot overwrite LIVE or a newer timeframe',async()=>{
 const e=setup();e.select('5m');e.window.AuraManualLiveHub.status='LIVE';e.send(snapshot);
 const response=tf=>({ok:true,json:async()=>({code:'00000',requestTime:now*1000,data:snapshot.windows[tf].bars.map(b=>[String(b.time*1000),b.open,b.high,b.low,b.close,b.volume,'0'])})});
 e.pending[0].resolve(response('15m'));e.pending[1].resolve(response('5m'));await new Promise(r=>setImmediate(r));
 assert.equal(e.run('currentData.timeframe'),'5m');assert.equal(e.created[0].values.length,201);assert.equal(e.el('feed-state').textContent,'LIVE');assert.match(e.el('chart-subtitle').textContent,/LIVE тикер/);
});
test('chart rejects stale or future frame receipt even with a fresh ticker',()=>{
 const s=structuredClone(snapshot);for(const received of [now-11,now+1]){s.windows['15m'].received_at=received;assert.equal(A.chartQuote(s,'15m',now).live,false)}
});

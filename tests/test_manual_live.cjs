const {test}=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs');
const A=require('../static/manual-live-analysis.js'),F=require('../static/manual-live-feed.js'),fixture=require('./fixtures/manual_live_synthetic.json'),now=fixture.now;
const clone=x=>structuredClone(x),row=b=>[String(b.time*1000),b.open,b.high,b.low,b.close,b.volume,'0'];
test('captured public Bitget REST response yields 200 closed candles without relaxing integrity',()=>{
 const body=require('./fixtures/manual_preview_bitget_15m.json'),at=body.requestTime/1000+1;
 const bars=F.history(body,'15m',at),closed=A.windowCheck(bars,900,at);
 a.equal(bars.length,201);a.equal(closed.length,200);
 a.ok(closed.every(b=>Number.isFinite(b.close)&&b.time%900===0));
 const bad=clone(body);bad.data[0][0]=String(Number(bad.data[0][0])+25000);
 a.throws(()=>F.history(bad,'15m',at),/INVALID_CANDLE/);
});
test('independent Python primitives match JS closed EMA/RSI/ATR/MACD on LONG/SHORT and every frame',()=>{
 for(const side of ['LONG','SHORT'])for(const tf of Object.keys(A.STEPS)){const bars=fixture.snapshots[side].windows[tf].bars.slice(0,-1),m=A.metrics(bars),r=fixture.reference[side+tf];for(const k of ['ema20','ema50','rsi','atr'])a.ok(Math.abs(m[k]-r[k])<1e-9,k);for(const [key,value]of [['macd',r.macd.line],['macd_signal',r.macd.signal],['histogram',r.macd.histogram]])a.ok(Math.abs(m[key]-value)<1e-9);}
});
test('LONG/SHORT are provisional; past levels, confirmed structure and fee/spread aware geometry',()=>{
 for(const side of ['LONG','SHORT']){const s=fixture.snapshots[side],v=A.analyze(s,now);a.equal(v.state,side);a.equal(v.preliminary,true);a.ok(v.scenario.net_rr>=1.5);a.ok(v.scenario.net_rr<v.scenario.gross_rr);a.ok(v.evidence.some(x=>x.stage==='PRELIMINARY'));a.ok(v.evidence.some(x=>x.stage==='CONFIRMED'));a.ok(v.frames['5m'].context.swings.every(x=>x.confirmed_at<=now));a.equal(v.read_only,true);}
});
test('a provisional signal can disappear without changing closed trend/pivots; history is bounded',()=>{
 const s=clone(fixture.snapshots.LONG),before=A.analyze(s,now);s.windows['5m'].bars.at(-1).volume=0;const after=A.analyze(s,now);a.equal(after.state,'WAIT');a.equal(after.reasons[0],'PARTIAL_VOLUME_NOT_SUPPORTING');a.deepEqual(before.frames['5m'].confirmed,after.frames['5m'].confirmed);a.deepEqual(before.frames['5m'].context,after.frames['5m'].context);
 const h=new A.History(3);for(let i=0;i<10;i++)h.add({...after,state:i%2?'LONG':'WAIT',generated_at:i});a.equal(h.items.length,3);h.add({...after,state:'LONG',generated_at:10});a.equal(h.items.length,3);
});
test('stale/future/foreign quotes, gaps, future bars and missing frames suppress recommendations',()=>{
 const changes=[s=>s.status='RECONNECTING',s=>s.quote.time-=6,s=>s.quote.received_at-=6,s=>s.quote.time+=1,s=>s.quote.source='SPOT',s=>s.quote.ask=0,s=>delete s.windows['4h'],s=>s.windows['5m'].bars.splice(50,1),s=>s.windows['5m'].bars.push({...s.windows['5m'].bars.at(-1),time:now+300}),s=>s.windows['1h'].event_at-=11];
 for(const fn of changes){const s=clone(fixture.snapshots.LONG);fn(s);const v=A.analyze(s,now);a.equal(v.state,'WAIT');a.equal(v.scenario,null);}
});
test('causal prefix is independent of future data; closed pivots require two later CLOSED bars',()=>{
 const s=clone(fixture.snapshots.LONG),v=A.analyze(s,now);const future=clone(s);future.windows['5m'].bars.push({...future.windows['5m'].bars.at(-1),time:now+1000,close:1});a.equal(A.analyze(future,now).state,'WAIT');a.deepEqual(A.analyze(s,now),v);
 const bars=s.windows['5m'].bars.slice(0,-1),p=A.swings(bars,300);a.ok(p.every(x=>x.index<=bars.length-3&&x.confirmed_at<=now));
});
test('history requires contiguous UTC and fresh Futures timestamps; duplicates/NaN fail',()=>{
 const bars=fixture.snapshots.LONG.windows['5m'].bars,body={code:'00000',requestTime:now*1000,data:bars.map(row)};a.equal(F.history(body,'5m',now).length,201);
 for(const mutate of [b=>b.data.splice(5,1),b=>b.data[5]=b.data[4],b=>b.requestTime-=11000,b=>b.data[0][4]='NaN']){const b=clone(body);mutate(b);a.throws(()=>F.history(b,'5m',now));}
});
test('same forming candle updates; late closed changes, gaps and rollback force recovery',()=>{
 const bars=fixture.snapshots.LONG.windows['5m'].bars,b={...bars.at(-1),high:bars.at(-1).high+2,volume:160};a.equal(F.merge(bars,[row(b)],300,now).at(-1).volume,160);
 a.throws(()=>F.merge(bars,[row({...b,volume:1})],300,now));a.throws(()=>F.merge(bars,[row({...bars.at(-2),close:bars.at(-2).close+1})],300,now));a.throws(()=>F.merge(bars,[row({...b,time:b.time+600})],300,now+600));
});
function harness(fetcher){const sockets=[],timeouts=[],intervals=[];let n=now;const hub=new F.Hub({clock:()=>n,fetcher,socket:url=>{a.equal(url,F.WS);const ws={readyState:1,sent:[],send(x){this.sent.push(x);},close(){}};sockets.push(ws);return ws;},timers:{setTimeout:f=>{timeouts.push(f);return timeouts.length;},clearTimeout(){},setInterval:f=>{intervals.push(f);return intervals.length;},clearInterval(){}}});return {hub,sockets,timeouts,intervals,setNow:x=>n=x};}
const historyFetch=async url=>{const tf=Object.keys(A.STEPS).find(tf=>url.includes('granularity='+({'1h':'1H','4h':'4H'}[tf]||tf)+'&'));a.ok(url.startsWith(F.REST));return {ok:true,json:async()=>({code:'00000',requestTime:now*1000,data:fixture.snapshots.LONG.windows[tf].bars.map(row)})};};
const tick={arg:{instType:'USDT-FUTURES',instId:'BTCUSDT',channel:'ticker'},action:'snapshot',ts:now*1000,data:[{bidPr:'14712.15',askPr:'14712.35',lastPr:'14712.25',ts:now*1000}]};
test('actual Hub subscription, fresh current candles + bid/ask => LIVE; disconnect/timeout => STALE and resnapshot',async()=>{
 const h=harness(historyFetch);h.hub.start();await new Promise(r=>setImmediate(r));const ws=h.sockets[0];ws.onopen();const sub=JSON.parse(ws.sent[0]);a.equal(sub.args.length,6);a.ok(sub.args.every(x=>x.instType==='USDT-FUTURES'&&x.instId==='BTCUSDT'));
 for(const [tf,channel]of Object.entries(F.CHANNELS))ws.onmessage({data:JSON.stringify({arg:{instType:'USDT-FUTURES',instId:'BTCUSDT',channel},action:'snapshot',ts:now*1000,data:[row(fixture.snapshots.LONG.windows[tf].bars.at(-1))]})});
 ws.onmessage({data:JSON.stringify(tick)});a.equal(h.hub.status,'LIVE');a.equal(h.hub.updates,6);a.equal(A.analyze({status:h.hub.status,windows:h.hub.windows,quote:h.hub.quote},now).state,'LONG');
 h.setNow(now+16);h.intervals[0]();a.equal(h.hub.status,'STALE');a.equal(h.hub.quote,null);h.hub.stop();
});
test('REST outage, bad ticker and stop/start generations cannot preserve stale actionable data',async()=>{
 const h=harness(async()=>{throw Error('timeout');});h.hub.start();await new Promise(r=>setImmediate(r));a.equal(h.hub.status,'STALE');a.equal(h.hub.quote,null);h.hub.stop();
 const j=harness(historyFetch);j.hub.start();await new Promise(r=>setImmediate(r));j.sockets[0].onmessage({data:JSON.stringify({...tick,arg:{...tick.arg,instType:'SPOT'}})});a.equal(j.hub.status,'STALE');j.hub.stop();
});
test('analysis/feed/UI contain no trade invocation or Active43 control',()=>{
 for(const path of ['static/manual-live-analysis.js','static/manual-live-feed.js','static/manual-live-ui.js']){const src=fs.readFileSync(path,'utf8');a.doesNotMatch(src,/\/api\/(active43|manual-paper)|innerHTML|private|ACCESS-KEY|method:\s*['"]POST/);}
});
test('official WS initial 500-row snapshot is accepted without dropping retained integrity checks',()=>{
 const bars=fixture.snapshots.LONG.windows['5m'].bars,first=bars[0],prefix=Array.from({length:299},(_,i)=>({...first,time:first.time-(299-i)*300})),rows=[...prefix,...bars].map(row);a.equal(rows.length,500);a.equal(F.merge(bars,rows,300,now).length,201);a.throws(()=>F.merge(bars,Array(1001).fill(rows[0]),300,now));
});
test('network timeout aborts all REST requests, never creates an actionable snapshot',async()=>{
 const h=harness((url,opt)=>new Promise((resolve,reject)=>opt.signal.addEventListener('abort',()=>reject(Error('timeout')))));h.hub.start();h.timeouts[0]();await new Promise(r=>setImmediate(r));a.equal(h.hub.status,'STALE');a.equal(h.hub.quote,null);a.equal(h.sockets.length,0);h.hub.stop();
});

test('preview provides validated HISTORY ONLY candles before websocket confirms fresh ticker',async()=>{
 const h=harness(historyFetch),seen=[];
 h.hub.onData=s=>seen.push({status:s.status,frames:Object.keys(s.windows||{}),quote:!!s.quote});
 h.hub.start();await new Promise(r=>setImmediate(r));
 a.ok(seen.some(s=>s.status==='RECONNECTING'&&s.frames.length===5&&!s.quote));
 a.equal(h.sockets.length,1);
 // Market decisions remain WAIT until ticker and all WS frames pass integrity checks.
 const hist=seen.find(s=>s.frames.length===5);
 a.equal(hist.status,'RECONNECTING');
 const source=fs.readFileSync('static/app.js','utf8');
 a.match(source,/const bars=fresh\?w\.bars:closed/);
 a.match(source,/HISTORY ONLY: показаны только закрытые свечи/);
 h.hub.stop();
});

test('delayed public message is ignored without disconnecting valid LIVE stream',async()=>{
 const h=harness(historyFetch);h.hub.start();await new Promise(r=>setImmediate(r));
 const ws=h.sockets[0];ws.onopen();
 const stale={...tick,ts:(now-20)*1000};
 ws.onmessage({data:JSON.stringify(stale)});
 a.equal(h.hub.status,'RECONNECTING');
 a.equal(h.hub.updates,0);a.equal(h.hub.ignoredStale,1);
 a.equal(h.hub.quote,null);
 a.equal(h.hub.diagnostic,'STALE_EVENT_IGNORED');
 const staleInner=structuredClone(tick);staleInner.data[0].ts=(now-20)*1000;
 ws.onmessage({data:JSON.stringify(staleInner)});
 a.equal(h.hub.updates,0);a.equal(h.hub.ignoredStale,2);
 for(const [tf,channel] of Object.entries(F.CHANNELS)){
  const bar=fixture.snapshots.LONG.windows[tf].bars.at(-1);
  ws.onmessage({data:JSON.stringify({arg:{instType:'USDT-FUTURES',instId:'BTCUSDT',channel},action:'snapshot',ts:now*1000,data:[row(bar)]})});
 }
 ws.onmessage({data:JSON.stringify(tick)});
 a.equal(h.hub.status,'LIVE');
 a.equal(h.hub.updates,6);
 a.equal(h.hub.ignoredStale,2);
 h.hub.stop();
});

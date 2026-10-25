/* Display-only public Bitget Futures feed. Never emits a strategy signal or order. */
(function(root){'use strict';
 const WS='wss://ws.bitget.com/v2/ws/public',REST='https://api.bitget.com/api/v2/mix/market/candles';
 const FRAMES={'1m':[60,'candle1m'],'5m':[300,'candle5m'],'15m':[900,'candle15m'],'1h':[3600,'candle1H']};
 function bar(row,step,now){
  if(!Array.isArray(row)||row.length<7||row.slice(0,6).some(x=>!['string','number'].includes(typeof x)||String(x).trim()===''))throw Error('INVALID_CANDLE');
  const [ms,open,high,low,close,volume]=row.slice(0,6).map(Number),time=ms/1000;
  if(!Number.isInteger(time)||time%step||time>now||now-time>step*1000||![open,high,low,close,volume].every(Number.isFinite)||Math.min(open,high,low,close)<=0||volume<0||low>Math.min(open,close)||high<Math.max(open,close)||low>high)throw Error('INVALID_CANDLE');
  return {time,open,high,low,close,volume};
 }
 function ema(bars,n){let value=bars[0]?.close;return bars.map((b,i)=>{value=i?value+2/(n+1)*(b.close-value):value;return {time:b.time,value};});}
 function snapshot(body,frame,now){
  const step=FRAMES[frame]?.[0];if(!step||body?.code!=='00000'||!Number.isFinite(Number(body.requestTime))||now*1000-Number(body.requestTime)>10000||now*1000-Number(body.requestTime)<-3000||!Array.isArray(body.data)||body.data.length<50||body.data.length>300)throw Error('INVALID_HISTORY');
  const bars=body.data.map(r=>bar(r,step,now)).sort((a,b)=>a.time-b.time);
  if(bars.some((b,i)=>i&&b.time-bars[i-1].time!==step)||bars.at(-1).time<Math.floor(now/step)*step-step)throw Error('HISTORY_GAP_OR_STALE');
  return bars;
 }
 function update(bars,msg,frame,now){
  const step=FRAMES[frame][0],arg=msg?.arg;
  if(arg?.instType!=='USDT-FUTURES'||arg.instId!=='BTCUSDT'||arg.channel!==FRAMES[frame][1]||!['snapshot','update'].includes(msg.action)||!Array.isArray(msg.data)||!msg.data.length||msg.data.length>1000||!Number.isFinite(Number(msg.ts))||now*1000-Number(msg.ts)>10000||now*1000-Number(msg.ts)<-3000)throw Error('INVALID_STREAM');
  const next=bars.slice();let live=false;
  for(const row of msg.data){const b=bar(row,step,now),last=next.at(-1);if(!last)throw Error('NEEDS_HISTORY');
   if(b.time<last.time)continue;
   if(b.time>last.time+step)throw Error('STREAM_GAP');
   if(b.time===last.time){if(b.volume<last.volume)throw Error('VOLUME_ROLLBACK');next[next.length-1]=b;}else next.push(b);
   if(b.time===Math.floor(now/step)*step)live=true;
  }
  return {bars:next.slice(-300),live};
 }
 class Feed{
  constructor({fetcher=root.fetch?.bind(root),socket=u=>new root.WebSocket(u),clock=()=>Date.now()/1000,onData=()=>{},onStatus=()=>{},timers=root}={}){Object.assign(this,{fetcher,socket,clock,onData,onStatus,timers});this.generation=0;this.retry=0;this.bars=[];this.running=false;}
  start(frame='5m'){if(!FRAMES[frame])throw Error('INVALID_FRAME');this.stop();this.frame=frame;this.running=true;this.connect();}
  stop(){this.onStatus('STALE');this.running=false;this.generation++;this.abort?.abort();this.ws?.close();this.timers.clearTimeout(this.reconnect);this.timers.clearInterval(this.watch);this.timers.clearTimeout(this.timeout);}
  async connect(){
   const gen=++this.generation;this.onStatus('RECONNECTING');this.abort=new AbortController();const abort=this.abort;
   const timeout=this.timers.setTimeout(()=>abort.abort(),10000);
   try{const r=await this.fetcher(REST+'?symbol=BTCUSDT&productType=USDT-FUTURES&granularity='+({'1h':'1H'}[this.frame]||this.frame)+'&limit=200',{signal:this.abort.signal,credentials:'omit',cache:'no-store',redirect:'error'});if(!r.ok)throw Error('HISTORY_HTTP');const body=await r.json();if(gen!==this.generation||!this.running)return;
    this.bars=snapshot(body,this.frame,this.clock());this.onData(this.bars);this.ws=this.socket(WS);this.lastLive=0;this.lastMessage=0;this.opened=this.clock();
    this.ws.onopen=()=>{if(gen!==this.generation)return;try{this.ws.send(JSON.stringify({op:'subscribe',args:[{instType:'USDT-FUTURES',channel:FRAMES[this.frame][1],instId:'BTCUSDT'}]}));}catch{this.fail(gen);}};
    this.ws.onmessage=e=>{if(gen!==this.generation)return;if(e.data==='pong')return;try{if(typeof e.data!=='string'||e.data.length>1048576)throw Error('STREAM_LIMIT');const m=JSON.parse(e.data);if(m.event==='error')throw Error('SUBSCRIPTION_ERROR');if(m.event==='subscribe')return;if(Number(m.ts)<this.lastMessage)return;const result=update(this.bars,m,this.frame,this.clock());this.lastMessage=Number(m.ts);this.bars=result.bars;this.onData(this.bars);if(result.live){this.lastLive=this.clock();this.retry=0;this.onStatus('LIVE');}}catch{this.fail(gen);}};
    this.ws.onerror=()=>this.fail(gen);this.ws.onclose=()=>this.fail(gen);
    this.watch=this.timers.setInterval(()=>{if(gen!==this.generation)return;if(this.clock()-(this.lastLive||this.opened)>15){this.fail(gen);return;}if(this.ws.readyState===1){try{this.ws.send('ping');}catch{this.fail(gen);}}},5000);
   }catch{this.fail(gen);}finally{this.timers.clearTimeout(timeout);}
  }
  fail(gen){if(gen!==this.generation||!this.running)return;this.generation++;this.onStatus('STALE');this.ws?.close();this.timers.clearInterval(this.watch);this.reconnect=this.timers.setTimeout(()=>{this.reconnect=null;if(this.running)this.connect();},Math.min(30000,1000*2**Math.min(this.retry++,5)));}
 }
 const api={Feed,bar,snapshot,update,ema,FRAMES,WS,REST};root.AuraBitgetLive=api;if(typeof module!=='undefined')module.exports=api;
 if(!root.document)return;
 const d=root.document,el=d.getElementById('a43-live-chart');if(!el||!root.LightweightCharts)return;
 const L=root.LightweightCharts,chart=L.createChart(el,{autoSize:true,height:300,layout:{background:{color:'#0b1424'},textColor:'#b7c6db'},timeScale:{timeVisible:true,secondsVisible:false}}),candles=chart.addSeries(L.CandlestickSeries,{upColor:'#42d6b0',downColor:'#fa788b',borderVisible:false}),e20=chart.addSeries(L.LineSeries,{color:'#42d6b0',lineWidth:1}),e50=chart.addSeries(L.LineSeries,{color:'#a295fa',lineWidth:1}),vol=chart.addSeries(L.HistogramSeries,{priceScaleId:'volume',priceFormat:{type:'volume'}});
 chart.priceScale('volume').applyOptions({scaleMargins:{top:.85,bottom:0}});
 const status=d.getElementById('a43-live-status'),price=d.getElementById('a43-live-price'),choice=d.getElementById('a43-live-timeframe');let fitted=false;
 const feed=new Feed({onStatus:s=>{status.textContent=s+(s==='STALE'?' · нет свежих данных':s==='RECONNECTING'?' · восстановление истории':' · формирующаяся свеча');if(s!=='LIVE')price.textContent='Цена не подтверждена';},onData:bars=>{candles.setData(bars);e20.setData(ema(bars,20));e50.setData(ema(bars,50));vol.setData(bars.map(b=>({time:b.time,value:b.volume,color:b.close>=b.open?'#42d6b055':'#fa788b55'})));price.textContent=String(bars.at(-1).close)+' USDT · '+new Date(bars.at(-1).time*1000).toISOString();if(!fitted){chart.timeScale().fitContent();fitted=true;}}});
 const panel=d.getElementById('active43-panel');function resume(){if(!d.hidden&&panel.open)feed.start(choice.value);else feed.stop();}
 choice.addEventListener('change',()=>{fitted=false;resume();});panel.addEventListener('toggle',resume);d.addEventListener('visibilitychange',resume);root.addEventListener('pageshow',resume);root.addEventListener('pagehide',()=>feed.stop());resume();
})(typeof window==='undefined'?globalThis:window);

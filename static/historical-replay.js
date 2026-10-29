/* Historical mode. Same pure strategy engine as LIVE; never publishes LIVE/account events. */
(function(root){'use strict';
const E=root.AuraManualStrategies||(typeof require==='function'?require('./manual-strategies.js'):null),O=root.AuraTradeOutcomes||(typeof require==='function'?require('./trade-outcomes.js'):null),STEPS={'15m':900,'1h':3600,'4h':14400};
function validate(payload){
 const step=STEPS[payload?.timeframe],b=payload?.bars;
 if(payload?.scope!=='HISTORICAL_REPLAY_ONLY'||payload.symbol!=='BTCUSDT'||payload.product!=='USDT-FUTURES'||!['BITGET_PUBLIC_HISTORY_API','BITGET_SAVED_REAL_ARCHIVE_2026_07_01_TO_10_29'].includes(payload.source)||!step||!Number.isInteger(payload.start)||!Number.isInteger(payload.end)||payload.start%step||payload.end%step||payload.end<=payload.start||payload.warmup!==200||!Array.isArray(b)||b.length<201||b.length>6200||b.length!==(payload.end-payload.start)/step+200)throw Error('INVALID_REPLAY_ENVELOPE');
 for(let i=0;i<b.length;i++){
  const x=b[i];if(x.time!==payload.start-200*step+i*step||!['open','high','low','close','volume'].every(k=>typeof x[k]==='number'&&Number.isFinite(x[k]))||Math.min(x.open,x.high,x.low,x.close)<=0||x.volume<0||x.low>Math.min(x.open,x.close)||x.high<Math.max(x.open,x.close))throw Error('INVALID_REPLAY_OHLCV_OR_GAP');
 }
 const m=payload.quote_model;if(m?.historical_bid_ask!==false||m.full_spread_bps!==2||m.slippage_bps_per_side!==5||m.fee_bps_per_side!==10)throw Error('UNREGISTERED_REPLAY_COST_MODEL');
 return step;
}
class Replay{
 constructor(payload){this.stepSize=validate(payload);this.payload=structuredClone(payload);this.bars=this.payload.bars;this.reset();}
 reset(){this.cursor=200;this.journal=[];this.latest=[];this.lastSignal=null;this.counts={processed:0,LONG:0,SHORT:0,REJECTED:0,WAIT:0};this.status='PAUSED';this.outcomes=new O.Analyzer(this.stepSize);}
 get total(){return this.bars.length-200;}
 get done(){return this.cursor>=this.bars.length;}
 get visible(){return this.bars.slice(Math.max(0,this.cursor-200),this.cursor);}
 next(){
  if(this.done){this.status='COMPLETE';return [];}
  const last=this.bars[this.cursor],now=last.time+this.stepSize;
  // Engine receives only the last 200 already-closed bars. No next-open or future extremes.
  const prefix=this.bars.slice(this.cursor-199,this.cursor+1),mid=last.close;
  const quote={bid:mid*(1-.0001),ask:mid*(1+.0001),time:now};
  const rows=E.evaluate(prefix,this.stepSize,now).map(x=>({...E.atQuote(x,quote,now,true),tf:this.payload.timeframe,
   mode:'HISTORICAL_REPLAY',fresh:false,quote_model:this.payload.quote_model,source:this.payload.source,
   historical_bid_ask:false,statistical_result:'NOT_EVALUATED'}));
  this.outcomes.advance(last);
  this.cursor++;this.counts.processed++;this.latest=rows;
  for(const x of rows){this.counts[x.state]++;if(x.setup!=='WAIT')this.journal.push(x);}
  const signals=rows.filter(x=>['LONG','SHORT'].includes(x.state));
  for(const s of signals)this.outcomes.register(s);
  if(this.done)this.outcomes.finalize();
  if(signals.length){this.lastSignal=signals[0];this.status='SIGNAL';}
  else if(this.done)this.status='COMPLETE';
  return rows;
 }
 outcomeReport(){return {...this.outcomes.report(),source:this.payload.source,input_sha256:this.payload.sha256,timeframe:this.payload.timeframe,start:this.payload.start,end:this.payload.end,processed_through:this.visible.at(-1)?.time+this.stepSize};}
 report(){return {version:'HISTORICAL_REPLAY_1',strategy_version:E.VERSION,scope:'HISTORICAL_REPLAY_ONLY',source:this.payload.source,input_sha256:this.payload.sha256,timeframe:this.payload.timeframe,start:this.payload.start,end:this.payload.end,quote_model:this.payload.quote_model,edge:'UNVALIDATED',statistical_result:'NOT_EVALUATED',counts:{...this.counts},processed_through:this.visible.at(-1)?.time+this.stepSize,journal:this.journal,outcomes:this.outcomeReport()};}
}
function csv(report){
 const fields=['id','strategy','tf','state','setup','formed_at','entry','stop','target','net_rr','edge','source','reasons','rejection','cancel'];
 const cell=v=>{let s=Array.isArray(v)?v.join('; '):String(v??'');if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
 return '\uFEFF'+[fields.join(','),...report.journal.map(x=>fields.map(k=>cell(x[k])).join(','))].join('\r\n');
}
const api={Replay,validate,csv,STEPS};root.AuraHistoricalReplay=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);

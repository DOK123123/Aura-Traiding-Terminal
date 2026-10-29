/* Reproduce: node research/manual_strategies/run.cjs <output.json> [1|1.5|2] */
'use strict';
const fs=require('node:fs'),zlib=require('node:zlib'),crypto=require('node:crypto'),E=require('../../static/manual-strategies.js');
const protocol=JSON.parse(fs.readFileSync(__dirname+'/protocol.json')),packed=fs.readFileSync(__dirname+'/../strategy_engine/bitget-2026-07-10-15m.json.gz'),raw=zlib.gunzipSync(packed),base=JSON.parse(raw),out=process.argv[2],multiplier=Number(process.argv[3]||1);
if(!out||![1,1.5,2].includes(multiplier))throw Error('OUTPUT_AND_REGISTERED_COST_REQUIRED');
const split=Date.parse(protocol.development_end)/1000,end=Date.parse(protocol.control_end)/1000;
function aggregate(step){const groups=new Map();for(const b of base){const t=Math.floor(b.time/step)*step;(groups.get(t)||groups.set(t,[]).get(t)).push(b);}return [...groups].filter(([t,v])=>v.length===step/900&&v.every((b,i)=>b.time===t+i*900)).map(([time,v])=>({time,open:v[0].open,high:Math.max(...v.map(x=>x.high)),low:Math.min(...v.map(x=>x.low)),close:v.at(-1).close,volume:v.reduce((s,x)=>s+x.volume,0)}));}
function metrics(xs){let equity=1,peak=1,dd=0;for(const x of xs){equity*=1+x.pnl;peak=Math.max(peak,equity);dd=Math.max(dd,1-equity/peak);}const wins=xs.filter(x=>x.pnl>0),gain=wins.reduce((s,x)=>s+x.pnl,0),loss=-xs.filter(x=>x.pnl<0).reduce((s,x)=>s+x.pnl,0);return {trades:xs.length,win_rate:xs.length?wins.length/xs.length:null,profit_factor:loss?gain/loss:null,expectancy:xs.length?xs.reduce((s,x)=>s+x.pnl,0)/xs.length:null,max_drawdown:xs.length?dd:null,net_return:xs.length?equity-1:null};}
const descriptive=xs=>({...metrics(xs),max_drawdown:null,net_return:null,aggregation:'POOLED_TRADES_NOT_A_PORTFOLIO'});
const observations=[],trades=[],coverage=[],examples={};
for(const [tf,step]of [['15m',900],['1h',3600],['4h',14400]]){
 const bars=aggregate(step),free={};coverage.push({tf,bars:bars.length,first:bars[0].time,last:bars.at(-1).time,first_decision:bars[200].time});
 for(let i=200;i<bars.length;i++){
  const now=bars[i].time;if(now>=end)break;
  // The forming bar is real, but evaluate excludes it at this timestamp.
  const signals=E.evaluate(bars.slice(i-200,i+1),step,now,{spread:bars[i-1].close*.0002*multiplier,multiplier});
  for(const s of signals){
   if(s.setup==='WAIT')continue;
   const period=now<split?'DEVELOPMENT':'REUSED_CONTROL';let rejection=s.rejection.join(';');
   if(i<(free[s.strategy]||0))rejection+=';POSITION_ALREADY_OPEN';
   // Quarantine any development trade that could cross the fixed boundary.
   if(i+15>=bars.length||now<split&&bars[i+15].time+step>split)rejection+=';INCOMPLETE_OR_CROSS_SPLIT_HORIZON';
   const sign=s.setup==='LONG'?1:-1,open=bars[i].open,spread=open*.0002*multiplier;
   if(open<s.zone.low||open>s.zone.high)rejection+=';NEXT_OPEN_OUTSIDE_ZONE';
   const costs=E.cost(open,s.stop,s.target,s.setup,spread,multiplier),geometry=sign*(open-s.stop)>0&&sign*(s.target-open)>0;
   if(!geometry||costs.net_rr<1.5)rejection+=';NEXT_OPEN_RISK_REJECTED';
   const item={id:s.id,tf,strategy:s.strategy,side:s.setup,at:now,period,state:rejection?'REJECTED':s.setup,rejection,entry:s.entry,stop:s.stop,target:s.target,reasons:s.reasons,cancel:s.cancel};observations.push(item);
   const key=s.strategy+':'+s.setup;if(!examples[key])examples[key]=item;
   if(rejection)continue;
   const entry=open*(1+sign*.0005*multiplier)+sign*spread/2;
   let exit=bars[i+15].close,reason='TIMEOUT',finish=i+15;
   for(let j=i;j<=i+15;j++){
    const b=bars[j],stop=sign===1?b.low<=s.stop:b.high>=s.stop,target=sign===1?b.high>=s.target:b.low<=s.target;
    if(stop||target){exit=stop?(sign===1?Math.min(s.stop,b.open):Math.max(s.stop,b.open)):s.target;reason=stop?'SL':'TP';finish=j;break;}
   }
   // Every fill pays an adverse half-spread/slippage and fee; ambiguous bar is SL.
   exit=exit*(1-sign*.0005*multiplier)-sign*spread/2;
   const pnl=(sign*(exit-entry)-.001*multiplier*(entry+exit))/entry;
   trades.push({...item,fill:entry,exit,end:bars[finish].time+step,pnl,reason});free[s.strategy]=finish+1;
  }
 }
}
const summary={};for(const strategy of Object.keys(E.names)){
 const found=observations.filter(x=>x.strategy===strategy),xs=trades.filter(x=>x.strategy===strategy);
 summary[strategy]={edge:'UNVALIDATED',verdict:'INSUFFICIENT_EVIDENCE',detected:{LONG:found.filter(x=>x.side==='LONG').length,SHORT:found.filter(x=>x.side==='SHORT').length},accepted:xs.length,rejected:found.filter(x=>x.state==='REJECTED').length,
  development:descriptive(xs.filter(x=>x.period==='DEVELOPMENT')),reused_control:descriptive(xs.filter(x=>x.period==='REUSED_CONTROL')),
  by_frame:Object.fromEntries(coverage.map(c=>[c.tf,{overall:metrics(xs.filter(x=>x.tf===c.tf)),reused_control:metrics(xs.filter(x=>x.tf===c.tf&&x.period==='REUSED_CONTROL')),by_side:Object.fromEntries(['LONG','SHORT'].map(side=>[side,metrics(xs.filter(x=>x.tf===c.tf&&x.side===side))]))}])),
  by_side:Object.fromEntries(['LONG','SHORT'].map(side=>[side,descriptive(xs.filter(x=>x.side===side))])),
  monthly:Object.fromEntries(['2026-07','2026-08','2026-09','2026-10'].map(month=>[month,metrics(xs.filter(x=>new Date(x.at*1000).toISOString().startsWith(month)))])),overall:descriptive(xs)};
}
let fixed_sample_stress=null;
if(multiplier>1){
 const baselinePath=require('node:path').join(require('node:path').dirname(out),'replay-base.json.gz');const baseline=JSON.parse(zlib.gunzipSync(fs.readFileSync(baselinePath)));
 const repriced=baseline.trades.map(x=>{const sign=x.side==='LONG'?1:-1,open=x.fill/(1+sign*.0006),rawExit=(x.exit+sign*open*.0001)/(1-sign*.0005),entry=open*(1+sign*.0006*multiplier),exit=rawExit*(1-sign*.0005*multiplier)-sign*open*.0001*multiplier;return {...x,pnl:(sign*(exit-entry)-.001*multiplier*(entry+exit))/entry};});
 fixed_sample_stress=Object.fromEntries(Object.keys(E.names).map(strategy=>[strategy,{reused_control:descriptive(repriced.filter(x=>x.strategy===strategy&&x.period==='REUSED_CONTROL')),by_frame:Object.fromEntries(coverage.map(c=>[c.tf,metrics(repriced.filter(x=>x.strategy===strategy&&x.tf===c.tf&&x.period==='REUSED_CONTROL'))]))}]));
}
const report=JSON.stringify({version:E.VERSION,protocol,protocol_sha256:crypto.createHash('sha256').update(fs.readFileSync(__dirname+'/protocol.json')).digest('hex'),source:'Bitget public USDT-M BTCUSDT historical 15m, preserved in PR before this change',input_sha256:crypto.createHash('sha256').update(raw).digest('hex'),multiplier,coverage,assumptions:{execution:'NEXT_OPEN_AFTER_CONFIRMED_CANDLE',sizing:'ONE_TIMES_NOTIONAL_COMPOUNDED_PER_STRATEGY_TF; combined metrics descriptive, not executable portfolio',ambiguous:'STOP_FIRST',funding:'NOT_MODELED',spread:'ASSUMED_2_BPS_NOT_HISTORICAL_QUOTES',independence:'REUSED_CONTROL_NOT_UNTOUCHED'},summary,fixed_sample_stress,examples,observations,trades},null,2);fs.writeFileSync(out,out.endsWith('.gz')?zlib.gzipSync(report,{mtime:0}):report);
console.log(JSON.stringify(summary));

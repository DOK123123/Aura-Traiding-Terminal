'use strict';
const O=require('../../static/trade-outcomes.js'),P=require('./protocol.json');
const resolved=t=>t.entered&&['TP','SL','TIMEOUT'].includes(t.outcome)&&Number.isFinite(t.r)&&Number.isFinite(t.pnl_usdt);
const WEEK=604800,MONDAY=345600; // 1970-01-05 00:00 UTC.
const week=t=>Math.floor((t-MONDAY)/WEEK);
function seed(key){let h=P.bootstrap.seed;for(const c of key)h=Math.imul(h^c.charCodeAt(0),16777619)>>>0;return h||1;}
function random(initial){let n=initial>>>0;return ()=>{n^=n<<13;n^=n>>>17;n^=n<<5;return (n>>>0)/4294967296;};}
function quantile(a,q){if(!a.length)return null;const v=a.slice().sort((a,b)=>a-b),p=(v.length-1)*q,lo=Math.floor(p);return v[lo]+(v[Math.ceil(p)]-v[lo])*(p-lo);}
function interval(samples,reps){return samples.length>=(1-P.bootstrap.undefined_replicates_max_fraction)*reps?[quantile(samples,.025),quantile(samples,.975)]:null;}
function confidence(trades,start,end,key='default',replicates=P.bootstrap.replicates){
 const closed=trades.filter(resolved),active=new Set(closed.map(t=>week(t.signal_time))),calendar=[];
 for(let w=week(start);w<=week(end-1);w++)calendar.push(closed.filter(t=>week(t.signal_time)===w));
 const base={method:P.bootstrap.method,confidence:.95,replicates,block_length_weeks:P.bootstrap.block_length_weeks,resolved:closed.length,active_weeks:active.size,calendar_weeks:calendar.length,effective_calendar_blocks:calendar.length/P.bootstrap.block_length_weeks,expectancy_R:null,win_rate:null,profit_factor:null,pnl_usdt:null,status:'INSUFFICIENT_EVIDENCE',caveat:'Exploratory, reused history, few blocks, cross-block/nonstationary dependence and multiple testing uncorrected. Not a validation probability.'};
 if(closed.length<P.bootstrap.minimum_resolved||active.size<P.bootstrap.minimum_active_weeks)return base;
 const rng=random(seed(key)),samples={expectancy_R:[],win_rate:[],profit_factor:[],pnl_usdt:[]},block=P.bootstrap.block_length_weeks;
 for(let n=0;n<replicates;n++){
  let count=0,sumR=0,sumP=0,wins=0,profit=0,loss=0;
  for(let pos=0;pos<calendar.length;){const initial=Math.floor(rng()*calendar.length);for(let j=0;j<block&&pos<calendar.length;j++,pos++)for(const t of calendar[(initial+j)%calendar.length]){count++;sumR+=t.r;sumP+=t.pnl_usdt;if(t.pnl_usdt>0){wins++;profit+=t.pnl_usdt;}else loss-=t.pnl_usdt;}}
  if(count){samples.expectancy_R.push(sumR/count);samples.win_rate.push(wins/count);samples.pnl_usdt.push(sumP);if(loss>0)samples.profit_factor.push(profit/loss);}
 }
 return {...base,status:'EXPLORATORY_INTERVAL_NOT_VALIDATED',...Object.fromEntries(Object.entries(samples).map(([k,v])=>[k,interval(v,replicates)])),defined_replicates:Object.fromEntries(Object.entries(samples).map(([k,v])=>[k,v.length]))};
}
function summarize(trades,start,end,key){const {curve,...m}=O.metrics(trades);return {...m,confidence:confidence(trades,start,end,key)};}
function groups(trades){const out={};for(const strategy of ['TREND_PULLBACK','BREAKOUT_RETEST','SR_REVERSAL'])for(const side of ['LONG','SHORT'])out[strategy+'|'+side]=trades.filter(t=>t.strategy===strategy&&t.direction===side);return out;}
function select(training,key,step,trainEnd){
 const gate=P.selection_gate,eligible=[],assessments=[];
 for(const [variant,runs]of Object.entries(training)){
  if(variant==='BASELINE'||P.sensitivity_only_not_selectable.includes(variant))continue;
  const purged=cost=>runs.filter(r=>r.cost===cost).flatMap(r=>r.trades).filter(t=>t.strategy+'|'+t.direction===key&&t.signal_time+97*step<trainEnd&&(t.exit_time===null||Number.isInteger(t.exit_time)&&t.exit_time+step<=trainEnd));
  const trades=purged(1),stress=purged(2),start=Math.min(...runs.map(r=>r.start)),m=summarize(trades,start,trainEnd,'select|'+key+'|'+variant),sm=summarize(stress,start,trainEnd,'selectStress|'+key+'|'+variant);
  const months=new Map();for(const t of trades.filter(resolved)){const k=new Date(t.signal_time*1000).toISOString().slice(0,7);months.set(k,(months.get(k)||0)+t.r);}
  const checks={MIN_TRAIN_RESOLVED:m.resolved>=gate.minimum_train_resolved,MIN_ACTIVE_WEEKS:m.confidence.active_weeks>=gate.minimum_train_active_weeks,TWO_POSITIVE_MONTHS:[...months.values()].filter(v=>v>0).length>=gate.minimum_train_positive_months,NET_PF:m.profit_factor!==null&&m.profit_factor>=gate.minimum_net_pf,POSITIVE_EXPECTANCY_CI:m.confidence.expectancy_R?.[0]>0,POSITIVE_STRESS2_EXPECTANCY:sm.expectancy_R>0&&sm.confidence.expectancy_R!==null};
  assessments.push({variant,checks,failed:Object.keys(checks).filter(k=>!checks[k]),resolved:m.resolved,active_weeks:m.confidence.active_weeks,positive_months:[...months.values()].filter(v=>v>0).length,profit_factor:m.profit_factor,expectancy_R:m.expectancy_R,expectancy_ci:m.confidence.expectancy_R,stress2_expectancy_R:sm.expectancy_R,stress2_expectancy_ci:sm.confidence.expectancy_R});
  if(Object.values(checks).every(Boolean))eligible.push({variant,score:sm.confidence.expectancy_R[0],resolved:m.resolved});
 }
 eligible.sort((a,b)=>b.score-a.score||a.variant.localeCompare(b.variant));return {selected:eligible[0]?.variant||null,eligible,assessments,reason:eligible.length?'FIXED_PRIOR_ONLY_GATE':'INSUFFICIENT_PRIOR_EVIDENCE_NO_SELECTION'};
}
module.exports={resolved,week,random,quantile,confidence,summarize,groups,select};

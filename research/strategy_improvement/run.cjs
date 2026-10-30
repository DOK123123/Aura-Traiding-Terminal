/* Offline, immutable-input research. Nothing imports this runner from the application. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),crypto=require('node:crypto'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const P=require('./protocol.json'),C=require('./candidates.cjs'),S=require('./statistics.cjs'),R=require('../../static/historical-replay.js'),O=require('../../static/trade-outcomes.js');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const stamp=x=>Date.parse(x)/1000;
function diagnose(t,f,bars,step){
 const sign=t.direction==='LONG'?1:-1,risk=Math.abs(t.entry-t.sl),future=bars.filter(b=>b.time>=t.signal_time&&b.time<t.signal_time+4*step),afterEntry=t.entry_time===null?[]:bars.filter(b=>b.time>t.entry_time&&b.time<=(t.exit_time??bars.at(-1).time));
 return {features:{...f,risk_atr:risk/f.atr,risk_percent:100*risk/t.entry,gross_RR:Math.abs(t.tp-t.entry)/risk,net_rr_at_signal:null,estimated_roundtrip_cost_to_risk:.0032*t.entry/risk},posthoc_only:{adverse_4bar_close_gt_1_ATR:future.some(b=>sign*(b.close-t.entry)<-f.atr),future_close_bars_observed:future.length,ohlc_envelope_MAE_R:afterEntry.length?Math.max(0,...afterEntry.map(b=>sign===1?(t.entry-b.low)/risk:(b.high-t.entry)/risk)):null,ohlc_envelope_MFE_R:afterEntry.length?Math.max(0,...afterEntry.map(b=>sign===1?(b.high-t.entry)/risk:(t.entry-b.low)/risk)):null,excursion_caveat:'Excludes entry candle; exit candle envelope can include post-exit extremes, not ordered executable excursions.',pre_fee_fill_R:t.entered&&t.exit_fill!==null?sign*(t.exit_fill-t.entry_fill)/risk:null,fee_R:t.fees_usdt===null?null:t.fees_usdt/risk}};
}
function buckets(trades){
 const out={};const classify=t=>{const f=t.diagnostic.features,h=t.diagnostic.posthoc_only;return {flat:f.flat?'FLAT_CAUSAL':'OTHER',structure:f.structure,trend:f.trend,ema_separation:f.ema_separation_atr<.5?'<0.5':f.ema_separation_atr<1?'0.5–1':'>=1',rsi:f.rsi<40?'<40':f.rsi<50?'40–50':f.rsi<60?'50–60':f.rsi<70?'60–70':'>=70',atr_percent:f.atr_percent<.3?'<0.3%':f.atr_percent<.8?'0.3–0.8%':'>=0.8%',risk_atr:f.risk_atr<2?'<2':f.risk_atr<3?'2–3':'>=3',cost_burden:f.estimated_roundtrip_cost_to_risk<.25?'<0.25':f.estimated_roundtrip_cost_to_risk<.5?'0.25–0.5':'>=0.5',utc_hour:String(Math.floor(f.utc_hour/6)*6).padStart(2,'0')+'–'+String(Math.floor(f.utc_hour/6)*6+5).padStart(2,'0'),reversal_POSTHOC:h.future_close_bars_observed<4?'CENSORED_<4_BARS':h.adverse_4bar_close_gt_1_ATR?'ADVERSE_CLOSE_AFTER_SIGNAL':'OTHER'};};
 for(const t of trades)for(const [dimension,bucket]of Object.entries(classify(t))){const key=[t.tf,t.strategy,t.direction,dimension,bucket].join('|');(out[key]??=[]).push(t);}
 return Object.entries(out).map(([key,t])=>{const {curve,...metrics}=O.metrics(t);return {key,...metrics,SL:t.filter(x=>x.outcome==='SL').length,TP:t.filter(x=>x.outcome==='TP').length,TIMEOUT:t.filter(x=>x.outcome==='TIMEOUT').length,mean_pre_fee_fill_R:mean(t.map(x=>x.diagnostic.posthoc_only.pre_fee_fill_R)),mean_fee_R:mean(t.map(x=>x.diagnostic.posthoc_only.fee_R))};});
}
function mean(v){v=v.filter(Number.isFinite);return v.length?v.reduce((s,x)=>s+x,0)/v.length:null;}
function run(out='work/strategy-improvement'){
 require('./baseline.cjs').verify();
 fs.mkdirSync(out,{recursive:true});const py=process.env.PYTHON||'python',runs=[],audits=[],inputs=[];
 for(const [tf,step]of Object.entries(P.frames))for(const period of P.periods){
  const start=stamp(period.start),end=stamp(period.end),payload=JSON.parse(execFileSync(py,['-c',`import json;from app.manual_preview.history import archive_history;print(json.dumps(archive_history(${JSON.stringify(tf)},${start},${end},${end})))`],{encoding:'utf8',maxBuffer:8e6})),replay=new R.Replay(payload),ledgers=[];
  for(const variant of P.candidates)for(const cost of P.cost_multipliers)ledgers.push({variant,cost,ledger:new O.Analyzer(step,Object.fromEntries(Object.entries(P.base_costs).map(([k,v])=>[k,v*cost])))});
  inputs.push({tf,period:period.name,sha256:payload.sha256,source:payload.source,bars:payload.bars.length,warmup:payload.warmup,start,end});const byID=new Map(),frameAudit={tf,period:period.name,decisions:0,baseline_counts:null,filters:{}};
  while(!replay.done){
   const index=replay.cursor,b=replay.bars[index],rows=replay.next(),plans=new Map();
   if(rows.some(C.accepted)){
    const prefix=replay.bars.slice(index-199,index+1),f=C.features(prefix,step);
    for(const row of rows.filter(C.accepted))byID.set(row.id,{f,row});
    for(const variant of P.candidates){const decisions=C.evaluateVariant(variant,rows,prefix,step,f);plans.set(variant,decisions);for(const d of decisions){const row=rows.find(x=>x.id===d.original_id),key=variant+'|'+row.strategy+'|'+row.state,counter=frameAudit.filters[key]??={baseline:0,accepted:0,reasons:{}};counter.baseline++;if(d.signal)counter.accepted++;for(const reason of d.reasons)counter.reasons[reason]=(counter.reasons[reason]||0)+1;}}
   }
   for(const l of ledgers){l.ledger.advance(b);for(const d of plans.get(l.variant)||[])if(d.signal)l.ledger.register(d.signal);}frameAudit.decisions++;
  }
  for(const l of ledgers){
   l.ledger.finalize();if(l.variant==='BASELINE'&&l.cost===1)assert.deepEqual(l.ledger.report().trades,replay.outcomeReport().trades);
   const trades=l.ledger.report().trades.map(t=>{const {f,row}=byID.get(t.id),diagnostic=diagnose(t,f,payload.bars,step);diagnostic.features.net_rr_at_signal=row.net_rr;return {...t,period:period.name,variant:l.variant,cost:l.cost,diagnostic};});
   runs.push({tf,step,period:period.name,role:period.role,start,end,variant:l.variant,cost:l.cost,trades});
  }
  frameAudit.baseline_counts=replay.counts;audits.push(frameAudit);console.log(tf+' '+period.name+' complete; accepted baseline '+(replay.counts.LONG+replay.counts.SHORT));
 }
 const summaries=[],monthly=[];
 for(const [tf,step]of Object.entries(P.frames))for(const variant of P.candidates)for(const cost of P.cost_multipliers){
  const matching=runs.filter(r=>r.tf===tf&&r.variant===variant&&r.cost===cost),trades=matching.flatMap(r=>r.trades),start=Math.min(...matching.map(r=>r.start)),end=Math.max(...matching.map(r=>r.end));
  for(const [group,t]of Object.entries(S.groups(trades)))summaries.push({tf,variant,cost,group,...S.summarize(t,start,end,[tf,variant,cost,group].join('|'))});
  for(const r of matching)for(const [group,t]of Object.entries(S.groups(r.trades)))monthly.push({tf,variant,cost,group,period:r.period,...S.summarize(t,r.start,r.end,[tf,variant,cost,group,r.period].join('|'))});
 }
 const folds=[];
 for(const [tf,step]of Object.entries(P.frames))for(const fold of P.walk_forward.folds){
  const training=Object.fromEntries(P.candidates.map(v=>[v,runs.filter(r=>r.tf===tf&&r.variant===v&&fold.train.includes(r.period))])),testRuns=runs.filter(r=>r.tf===tf&&r.period===fold.test),testStart=testRuns[0].start;
  for(const group of Object.keys(S.groups([]))){
   const selection=S.select(training,group,step,testStart),purgedCounts=Object.fromEntries(P.candidates.map(v=>[v,training[v].filter(r=>r.cost===1).flatMap(r=>r.trades).filter(t=>t.strategy+'|'+t.direction===group&&t.signal_time+97*step<testStart).filter(S.resolved).length]));
   const tests=P.cost_multipliers.map(cost=>{const t=selection.selected?testRuns.filter(r=>r.variant===selection.selected&&r.cost===cost).flatMap(r=>r.trades).filter(t=>t.strategy+'|'+t.direction===group):[];return {cost,...S.summarize(t,testStart,testRuns[0].end,['WF',tf,group,fold.test,cost].join('|'))};});const variant_tests=monthly.filter(r=>r.tf===tf&&r.group===group&&r.period===fold.test);folds.push({tf,group,train:fold.train,test:fold.test,train_end:testStart,purged_training_resolved:purgedCounts,...selection,tests,variant_tests});
  }
 }
 const baseline=runs.filter(r=>r.variant==='BASELINE'&&r.cost===1).flatMap(r=>r.trades),diagnostics=buckets(baseline),examples=[];
 for(const tf of Object.keys(P.frames))for(const [group,t]of Object.entries(S.groups(baseline.filter(x=>x.tf===tf))))for(const category of ['POSITIVE_NET','NEGATIVE_NET']){const sample=t.filter(S.resolved).find(t=>category==='POSITIVE_NET'?t.r>0:t.r<0);examples.push({tf,group,category,trade:sample||null,reason:sample?'FIRST_CHRONOLOGICAL_EXAMPLE_NOT_MAX_PNL':'NO_MATCHING_REAL_TRADE'});}
 const shortlist=[];
 for(const m of summaries.filter(x=>x.variant!=='BASELINE'&&!P.sensitivity_only_not_selectable.includes(x.variant)&&x.cost===2)){
  const tests=monthly.filter(x=>x.tf===m.tf&&x.variant===m.variant&&x.cost===2&&x.group===m.group&&['2026-09','2026-10'].includes(x.period));
  if(m.resolved>=P.forward_shortlist_gate.minimum_resolved_per_strategy_side_frame&&m.confidence.expectancy_R?.[0]>0&&tests.length===2&&tests.every(x=>x.expectancy_R>0))shortlist.push({tf:m.tf,group:m.group,variant:m.variant,status:'REUSED_DATA_FORWARD_ONLY_NEVER_VALIDATED'});
 }
 const source=fs.readFileSync(P.source);
 const manifest={version:P.version,baseline_commit:P.baseline_commit,protocol_sha256:sha(fs.readFileSync(path.join(__dirname,'protocol.json'))),input_archive_sha256:sha(source),protected_files:require('./baseline.cjs').digests(),inputs,candidate_count:P.candidates.length,cost_scenarios:P.cost_multipliers,history_independence:P.data_independence,verdict:shortlist.length?'FORWARD_RESEARCH_SHORTLIST_UNVALIDATED':'NO_EDGE_FOUND',shortlist,independent_validation:'INSUFFICIENT_EVIDENCE',portfolio:'NONE',diagnostic_causality:'Features causal; posthoc annotations never passed into candidate evaluation.',interval_caveat:'3-week circular blocks, sparse reused regimes; no multiple-comparison correction or guarantee of stationarity. CI not evidence of independent edge.'};
 const full={manifest,summaries,monthly,folds,audits,diagnostics,examples,runs};fs.writeFileSync(path.join(out,'results.json.gz'),zlib.gzipSync(JSON.stringify(full)));
 const baselineReasons=[];for(const tf of Object.keys(P.frames))for(const [group,t]of Object.entries(S.groups(baseline.filter(x=>x.tf===tf)))){const closed=t.filter(S.resolved),{curve,...metrics}=O.metrics(t);baselineReasons.push({group:tf+'|'+group,...metrics,TP:t.filter(x=>x.outcome==='TP').length,SL:t.filter(x=>x.outcome==='SL').length,UNKNOWN:t.filter(x=>x.outcome==='UNKNOWN').length,timeout_filled:t.filter(x=>x.outcome==='TIMEOUT'&&x.entered).length,timeout_unfilled:t.filter(x=>x.outcome==='TIMEOUT'&&!x.entered).length,notes:Object.fromEntries([...new Set(t.map(x=>x.note))].map(note=>[note,t.filter(x=>x.note===note).length])),mean_pre_fee_fill_R:mean(closed.map(x=>x.diagnostic.posthoc_only.pre_fee_fill_R)),mean_fee_R:mean(closed.map(x=>x.diagnostic.posthoc_only.fee_R))});}
 const compact={manifest,summaries,monthly,folds,audits,diagnostics,examples,baselineReasons};fs.writeFileSync(path.join(out,'summary.json.gz'),zlib.gzipSync(JSON.stringify(compact)));require('./report.cjs').writeReports(compact,out);console.log(JSON.stringify({verdict:manifest.verdict,shortlist,groups:summaries.length,monthly:monthly.length,folds:folds.length,output:out}));return compact;
}
if(require.main===module)run(process.argv[2]);module.exports={run,diagnose,buckets};

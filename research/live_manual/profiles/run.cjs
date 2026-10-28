/* Pure local minute-prefix research. No network, credentials or execution client. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),A=require('../../../static/manual-live-analysis.js'),{Model}=require('./model.cjs');
const args=process.argv.slice(2),arg=k=>args[args.indexOf(k)+1];if(!args.includes('--input')||!args.includes('--output'))throw Error('LOCAL_INPUT_AND_NEW_OUTPUT_REQUIRED');
const out=path.resolve(arg('--output'));if(fs.existsSync(out))throw Error('NEW_OUTPUT_REQUIRED');
const protocolPath=path.join(__dirname,'protocol.json'),protocol=JSON.parse(fs.readFileSync(protocolPath)),input=JSON.parse(fs.readFileSync(arg('--input'))),hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
if(input.source!=='BITGET_USDT_FUTURES_BTCUSDT'||input.rows.length>600000)throw Error('SOURCE_OR_LIMIT');
const sourceFiles=['static/manual-live-analysis.js','research/live_manual/profiles/run.cjs','research/live_manual/profiles/model.cjs'],initialHashes=Object.fromEntries(sourceFiles.map(f=>[f,hash(path.join(__dirname,'../../..',f))])),allMinutes=args.includes('--all-minutes'),cadence=allMinutes?JSON.parse(fs.readFileSync(path.join(__dirname,'cadence_audit.json'))):null;
if(allMinutes&&cadence.base_protocol_sha256!==hash(protocolPath))throw Error('CADENCE_PROTOCOL_MISMATCH');
const quantiles={},start=Date.parse(protocol.sample.start)/1000,end=Date.parse(protocol.sample.end_exclusive)/1000,book={closed:{},partial:{}},results={},stats={},events=[],allTrades=[],allEquity=[],sims={};let last=null,currentPeriod=null,observations=0,legacyDisagreements=0,withdrawals={},lastState={};
for(const tf of Object.keys(A.STEPS))book.closed[tf]=[];
const periodOf=t=>new Date(t*1000).toISOString().slice(0,7),blank=()=>({observations:0,states:{LONG:0,SHORT:0,WAIT:0},first_wait:{},all_failed:{},warnings:{},conflicting_4h:0,only_4h_block:0}),inc=(obj,k)=>obj[k]=(obj[k]||0)+1;
function finish(){if(!last||!currentPeriod)return;for(const [key,sim]of Object.entries(sims)){sim.finish(last);results[currentPeriod+'_'+key]=sim.metrics();allTrades.push(...sim.trades.map(t=>({...t,period:currentPeriod,profile:key.split('_')[0],cost:Number(key.split('_')[1])})));allEquity.push(...sim.equity.map(t=>({...t,period:currentPeriod,profile:key.split('_')[0],cost:Number(key.split('_')[1])})));}}
for(const row of input.rows){
 const [time,open,high,low,close,volume]=row,b={time,open,high,low,close,volume};if(last&&time-last.time!==60)throw Error('GAP_DUPLICATE_OR_ORDER');if(time>=end)break;
 if(time>=start){const period=periodOf(time);if(period!==currentPeriod){finish();currentPeriod=period;for(const profile of Object.keys(A.PROFILES))for(const cost of [1,1.5,2])sims[profile+'_'+cost]=new Model(protocol,cost);}for(const sim of Object.values(sims))sim.atOpen(b);}
 for(const [tf,step]of Object.entries(A.STEPS)){let p=book.partial[tf];const at=Math.floor(time/step)*step;if(p&&p.time!==at){book.closed[tf].push(p);book.closed[tf]=book.closed[tf].slice(-200);p=null;}book.partial[tf]={time:at,open:p?p.open:open,high:p?Math.max(p.high,open):open,low:p?Math.min(p.low,open):open,close:open,volume:p?p.volume:0};}
 if(time>=start&&(allMinutes||protocol.sample.observation_minute_offsets.includes(Math.floor(time/60)%5))&&Object.values(book.closed).every(x=>x.length===200)){
  const now=time+protocol.sample.publication_delay_assumed_seconds,snapshot={status:'LIVE',windows:Object.fromEntries(Object.keys(A.STEPS).map(tf=>[tf,{bars:[...book.closed[tf],book.partial[tf]],event_at:now,received_at:now}])),quote:{source:input.source,bid:open*.9999,ask:open*1.0001,last:open,time:now,received_at:now}},values=A.analyzeProfiles(snapshot,now),f=values.CONSERVATIVE.frames['1h'].confirmed,strength=Math.abs(f.ema20-f.ema50)/f.atr,regime=f.atr/f.close>=.01?'HIGH_VOL':strength>=.5&&f.trend!=='NEUTRAL'?'TREND_'+(f.trend==='LONG'?'UP':'DOWN'):'RANGE';
  const legacy=A.legacyAnalyze(snapshot,now);if(legacy.state!==values.CONSERVATIVE.state)legacyDisagreements++;
  observations++;
  for(const [profile,v]of Object.entries(values)){
   const id=profile+':'+Math.floor(time/300)*300,reference=v.potentials.find(x=>x.side===f.trend)||v.nearest;
   for(const key of ['ALL',currentPeriod,regime,currentPeriod+'/'+regime]){const s=stats[profile+'/'+key]??=blank();s.observations++;s.states[v.state]++;if(v.state==='WAIT')inc(s.first_wait,v.reasons[0]);for(const code of v.blockers)inc(s.all_failed,code);for(const code of v.warnings)inc(s.warnings,code);if(reference?.checks.some(c=>c.code==='CONFLICTING_4H'&&!c.passed))s.conflicting_4h++;if(v.blockers.length===1&&v.blockers[0]==='CONFLICTING_4H')s.only_4h_block++;}
   const qs=quantiles[profile]??={atr_pct:[],net_rr:[],all_other_checks_pass_rr:[],rr_only_block:0};qs.atr_pct.push(v.frames['5m'].preliminary.atr/v.frames['5m'].preliminary.close*100);if(reference?.scenario){qs.net_rr.push(reference.scenario.net_rr);if(reference.checks.filter(c=>c.code!=='INSUFFICIENT_RR_AFTER_COSTS').every(c=>c.passed)){qs.all_other_checks_pass_rr.push(reference.scenario.net_rr);if(v.blockers.includes('INSUFFICIENT_RR_AFTER_COSTS'))qs.rr_only_block++;}}
   if(lastState[id]&&lastState[id]!=='WAIT'&&v.state!==lastState[id])inc(withdrawals,profile);lastState[id]=v.state;
   if(v.state!=='WAIT')events.push({time:now,profile,period:currentPeriod,regime,state:v.state,entry:v.scenario.reference_entry,stop:v.scenario.stop_loss,target:v.scenario.take_profit,net_rr:v.scenario.net_rr,warnings:v.warnings.join(';')});
   for(const cost of [1,1.5,2])sims[profile+'_'+cost].signal(v,now,id,regime);
  }
 }
 if(time>=start)for(const sim of Object.values(sims))sim.atClose(b);
 for(const tf of Object.keys(A.STEPS)){const p=book.partial[tf];book.partial[tf]={...p,high:Math.max(p.high,high),low:Math.min(p.low,low),close,volume:p.volume+volume};}
 last=b;
}
finish();if(!observations)throw Error('NO_OBSERVATIONS');if(legacyDisagreements)throw Error('CONSERVATIVE_CHANGED');
for(const [file,digest]of Object.entries(initialHashes))if(hash(path.join(__dirname,'../../..',file))!==digest)throw Error('SOURCE_CHANGED_DURING_RUN');
for(const qs of Object.values(quantiles))for(const key of ['atr_pct','net_rr','all_other_checks_pass_rr']){const a=qs[key].sort((a,b)=>a-b);qs[key]={n:a.length,p10:a.length?a[Math.floor((a.length-1)*.1)]:null,p50:a.length?a[Math.floor((a.length-1)*.5)]:null,p90:a.length?a[Math.floor((a.length-1)*.9)]:null};}
fs.mkdirSync(out,{recursive:true});function csv(name,rows){const keys=rows.length?Object.keys(rows[0]):['id'],cell=x=>JSON.stringify(x??'');fs.writeFileSync(path.join(out,name),[keys.join(','),...rows.map(r=>keys.map(k=>cell(typeof r[k]==='object'?JSON.stringify(r[k]):r[k])).join(','))].join('\n')+'\n');}
csv('comparison.csv',Object.entries(results).map(([key,v])=>({key,...v,rejections:JSON.stringify(v.rejections)})));csv('signals.csv',events);csv('trades.csv',allTrades);csv('equity.csv',allEquity);
const summary={protocol,protocol_sha256:hash(protocolPath),code_sha256:initialHashes,cadence_audit:cadence,observation_offsets:allMinutes?[0,1,2,3,4]:protocol.sample.observation_minute_offsets,quantiles,input_manifest:input.manifest,observations,legacyDisagreements,withdrawals,stats,results,verdict:'INSUFFICIENT_EVIDENCE',independent_oos:false,production_changed:false};fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify(summary,null,2)+'\n');console.log(JSON.stringify({observations,legacyDisagreements,results}));

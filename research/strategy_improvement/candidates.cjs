/* Offline hypotheses only. No registration in LIVE, no networking or account imports. */
'use strict';
const A=require('../../static/manual-live-analysis.js'),E=require('../../static/manual-strategies.js'),P=require('./protocol.json');
const accepted=s=>s.state==='LONG'||s.state==='SHORT';
function efficiency(b,n=20){const v=b.slice(-n-1).map(x=>x.close);if(v.length<n+1)throw Error('ER_WARMUP');let path=0;for(let i=1;i<v.length;i++)path+=Math.abs(v[i]-v[i-1]);return path?Math.abs(v.at(-1)-v[0])/path:0;}
function features(b,step){
 if(b.length!==200)throw Error('RESEARCH_PREFIX_200_REQUIRED');const m=A.metrics(b),previous=A.metrics(b.slice(0,-5)),z=b.at(-1),p=b.at(-2),range=z.high-z.low,structure=A.context(b.slice(0,-1),step).structure,mean=b.slice(-21,-1).reduce((n,x)=>n+x.volume,0)/20;
 return {...m,er20:efficiency(b),ema_separation_atr:Math.abs(m.ema20-m.ema50)/m.atr,ema50_slope_atr:(m.ema50-previous.ema50)/m.atr,atr_percent:100*m.atr/z.close,structure,body_fraction:range?Math.abs(z.close-z.open)/range:0,close_location:range?(z.close-z.low)/range:.5,outside_bar:z.high>p.high&&z.low<p.low,volume_ratio:mean?z.volume/mean:null,utc_hour:new Date((z.time+step)*1000).getUTCHours(),flat:efficiency(b)<.20&&Math.abs(m.ema20-m.ema50)/m.atr<.50};
}
function breakoutConfirmation(b,step,side){
 const long=side==='LONG',z=b.at(-1),f=features(b,step),rules=P.rules.breakout;let best=null;
 for(let j=b.length-6;j<b.length-1;j++){
  const before=b.slice(0,j),ctx=A.context(before,step),m=A.metrics(before),level=ctx.swings.filter(x=>x.kind===(long?'HIGH':'LOW')).at(-1)?.price;
  if(!Number.isFinite(level)||!(m.atr>0))continue;
  const bb=b[j],mean=before.slice(-20).reduce((s,x)=>s+x.volume,0)/20;
  const sign=long?1:-1,crossed=long?b[j-1].close<=level:b[j-1].close>=level;
  const retest=long?z.low<=level+.25*f.atr&&z.low>=level-.5*f.atr&&z.close>level+.1*f.atr&&z.close>z.open:z.high>=level-.25*f.atr&&z.high<=level+.5*f.atr&&z.close<level-.1*f.atr&&z.close<z.open;
  if(!crossed||sign*(bb.close-level)<=.1*m.atr||!retest)continue;
  const checks={BREAK_CLEARANCE:sign*(bb.close-level)>=rules.clearance_atr*m.atr,BREAK_VOLUME:mean>0&&bb.volume>=rules.break_volume_ratio_min*mean,INTERMEDIATE_CLOSED_BAR:b.length-j-2>=rules.min_intermediate_closed_bars,LEVEL_HELD:b.slice(j+1,-1).every(x=>sign*(x.close-level)>=0),RETEST_VOLUME:f.volume_ratio!==null&&f.volume_ratio>=rules.retest_volume_ratio_min,RETEST_CLOSE_LOCATION:(long?f.close_location:1-f.close_location)>=rules.close_location_min};
  const evidence={level,break_time:bb.time,confirmed_level_latest_time:before.at(-1).time+step,checks,failed:Object.keys(checks).filter(k=>!checks[k])};
  if(!best||evidence.failed.length<best.failed.length)best=evidence;
 }
 return best||{failed:['NO_CAUSAL_BREAK_RETEST'],checks:{}};
}
function evaluateVariant(id,rows,b,step,f=features(b,step)){
 if(b.length!==200||rows.filter(accepted).some(x=>x.formed_at!==b.at(-1).time+step))throw Error('NONCAUSAL_RESEARCH_INPUT');
 if(!P.candidates.includes(id))throw Error('UNREGISTERED_RESEARCH_VARIANT');
 const combined=id.startsWith('COMBINED'),perturb=id==='COMBINED_LOOSE'?P.rules.loose:id==='COMBINED_STRICT'?P.rules.strict:{};
 return rows.filter(accepted).map(original=>{
  const s=structuredClone(original),sign=s.state==='LONG'?1:-1,reasons=[];let evidence=null;
  if((id==='TREND_REGIME'||combined)&&s.strategy==='TREND_PULLBACK'){
   if(f.er20<(perturb.regime_efficiency_min??P.rules.regime.efficiency_min))reasons.push('REGIME_LOW_EFFICIENCY');
   if(f.ema_separation_atr<(perturb.regime_ema_min??P.rules.regime.ema_separation_atr_min))reasons.push('REGIME_WEAK_EMA_SEPARATION');
   if(sign*f.ema50_slope_atr<P.rules.regime.slope_direction_min)reasons.push('REGIME_OPPOSED_EMA_SLOPE');
  }
  if((id==='BREAKOUT_CONFIRM'||combined)&&s.strategy==='BREAKOUT_RETEST'){evidence=breakoutConfirmation(b,step,s.state);reasons.push(...evidence.failed);}
  if(id==='QUALITY'||combined){
   if(f.body_fraction<(perturb.body_min??P.rules.quality.body_fraction_min))reasons.push('QUALITY_SMALL_BODY');
   if((sign===1?f.close_location:1-f.close_location)<P.rules.quality.close_location_min)reasons.push('QUALITY_WEAK_CLOSE');
   if(f.outside_bar)reasons.push('QUALITY_OUTSIDE_BAR');
   if(rows.some(x=>accepted(x)&&x.state!==s.state))reasons.push('QUALITY_OPPOSED_STRATEGY');
   if(s.entry*.0032/Math.abs(s.entry-s.stop)>P.rules.quality.estimated_roundtrip_cost_to_stop_max)reasons.push('QUALITY_COST_BURDEN');
  }
  if(id==='ATR_EXITS'||combined){
   const distance=Math.max(Math.abs(s.entry-s.stop),(perturb.minimum_stop_atr??P.rules.atr_exits.minimum_stop_atr)*f.atr),rr=f.er20>=P.rules.atr_exits.efficiency_switch?P.rules.atr_exits.target_R_efficient:P.rules.atr_exits.target_R_other;
   s.stop=s.entry-sign*distance;s.target=s.entry+sign*rr*distance;
   const now=s.formed_at,mid=b.at(-1).close,quote={bid:mid*(1-.0001),ask:mid*(1+.0001),time:now};
   if(!['entry','stop','target'].every(k=>Number.isFinite(s[k])&&s[k]>0))reasons.push('RESEARCH_INVALID_GEOMETRY');
   const gated=E.atQuote({...s,rejection:[]},quote,now,true);if(!accepted(gated))reasons.push(...gated.rejection);Object.assign(s,gated,{fresh:false});
  }
  return {original_id:original.id,variant:id,signal:reasons.length?null:s,reasons,evidence};
 });
}
module.exports={features,efficiency,breakoutConfirmation,evaluateVariant,accepted};

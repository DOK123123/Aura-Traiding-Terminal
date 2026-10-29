/* Closed-candle technical hypotheses. Pure analysis: no execution or account authority. */
(function(root){'use strict';
const A=root.AuraManualLiveAnalysis||(typeof require==='function'?require('./manual-live-analysis.js'):null);
const VERSION='MANUAL_STRATEGIES_1',names={TREND_PULLBACK:'Trend Pullback',BREAKOUT_RETEST:'Breakout + Retest',SR_REVERSAL:'Support/Resistance Reversal'};
const finite=Number.isFinite;
function cost(entry,stop,target,side,spread=0,multiplier=1){
 const sign=side==='LONG'?1:-1,slip=.0005*multiplier,fee=.001*multiplier;
 const e=entry*(1+sign*slip)+sign*spread/2,s=stop*(1-sign*slip)-sign*spread/2,t=target*(1-sign*slip)-sign*spread/2;
 const loss=sign*(e-s)+fee*(e+s),gain=sign*(t-e)-fee*(e+t);
 return {net_rr:loss>0?Math.max(0,gain)/loss:null,fee_per_side:fee,slippage_per_side:slip,spread,funding:'NOT_MODELED'};
}
function candidates(b,step){
 const z=b.at(-1),p=b.at(-2),prior=b.slice(0,-1),m=A.metrics(b),pm=A.metrics(prior),ctx=A.context(prior,step),atr=m.atr;
 const mean=prior.slice(-20).reduce((s,x)=>s+x.volume,0)/20,bull=z.close>z.open,bear=z.close<z.open;
 const result=Object.keys(names).map(strategy=>({strategy,side:'WAIT',reasons:['Условия этой стратегии на закрытых свечах не выполнены'],technical_strength:null}));
 const put=(i,side,reasons,anchor)=>Object.assign(result[i],{side,reasons,anchor,technical_strength:'RULES_MET · не вероятность прибыли'});
 const touch=side=>side==='LONG'?p.low<=Math.max(pm.ema20,pm.ema50)+.25*atr&&p.high>=Math.min(pm.ema20,pm.ema50)-.25*atr:p.high>=Math.min(pm.ema20,pm.ema50)-.25*atr&&p.low<=Math.max(pm.ema20,pm.ema50)+.25*atr;
 if(m.trend==='LONG'&&ctx.structure==='HH_HL'&&touch('LONG')&&bull&&z.close>p.high&&m.rsi>=45&&m.rsi<=70)
  put(0,'LONG',['EMA20 > EMA50; подтверждённая HH/HL','Откат к EMA20/50 и закрытие выше предыдущего high','RSI14 45–70; подтверждение только закрытой свечой'],Math.min(p.low,z.low));
 if(m.trend==='SHORT'&&ctx.structure==='LH_LL'&&touch('SHORT')&&bear&&z.close<p.low&&m.rsi>=30&&m.rsi<=55)
  put(0,'SHORT',['EMA20 < EMA50; подтверждённая LH/LL','Откат к EMA20/50 и закрытие ниже предыдущего low','RSI14 30–55; подтверждение только закрытой свечой'],Math.max(p.high,z.high));
 // The level must already be confirmed BEFORE the breakout, never by retest bars.
 for(let j=b.length-6;j<b.length-1&&result[1].side==='WAIT';j++){
  const before=b.slice(0,j),breakbar=b[j],levelContext=A.context(before,step),bm=A.metrics(before);
  const volume=before.slice(-20).reduce((s,x)=>s+x.volume,0)/20;
  for(const side of ['LONG','SHORT']){
   const long=side==='LONG',level=levelContext.swings.filter(x=>x.kind===(long?'HIGH':'LOW')).at(-1)?.price;
   if(!finite(level)||!bm.atr||volume<=0||breakbar.volume<1.2*volume)continue;
   const broken=long?breakbar.close>level+.1*bm.atr&&b[j-1].close<=level:breakbar.close<level-.1*bm.atr&&b[j-1].close>=level;
   const held=b.slice(j+1,-1).every(x=>long?x.close>=level-.25*bm.atr:x.close<=level+.25*bm.atr);
   const retest=long?z.low<=level+.25*atr&&z.low>=level-.5*atr&&z.close>level+.1*atr&&bull:z.high>=level-.25*atr&&z.high<=level+.5*atr&&z.close<level-.1*atr&&bear;
   if(broken&&held&&retest){put(1,side,['Пробой заранее подтверждённого swing '+level.toFixed(2),'Объём пробоя ≥1.2 среднего предыдущих 20 свечей','Повторный тест удержан; закрытие вернулось за уровень'],long?Math.min(z.low,level):Math.max(z.high,level));break;}
  }
 }
 for(const side of ['LONG','SHORT']){
  const long=side==='LONG',points=ctx.swings.filter(x=>x.kind===(long?'LOW':'HIGH')),level=points.at(-1)?.price;
  if(!finite(level)||points.filter(x=>Math.abs(x.price-level)<=.5*atr).length<2||mean<=0||z.volume<mean)continue;
  const body=Math.abs(z.close-z.open),wick=long?Math.min(z.open,z.close)-z.low:z.high-Math.max(z.open,z.close);
  const reversal=long?z.low<=level+.5*atr&&z.low>=level-.5*atr&&bull&&z.close>p.high&&pm.rsi<=40&&m.rsi>pm.rsi:z.high>=level-.5*atr&&z.high<=level+.5*atr&&bear&&z.close<p.low&&pm.rsi>=60&&m.rsi<pm.rsi;
  if(reversal&&wick>=body&&body>=.1*atr)put(2,side,['Зона '+level.toFixed(2)+' подтверждена ≥2 прошлыми swing','RSI выходит из экстремума; разворотная тень ≥тела','Импульс за экстремум предыдущей свечи; объём ≥среднего','Предшествующая структура: '+ctx.structure],long?Math.min(z.low,level):Math.max(z.high,level));
 }
 return {result,metrics:m};
}
function evaluate(b,step,now,{spread=0,multiplier=1}={}){
 const closed=A.windowCheck(b,step,now).slice(-200);if(closed.length<200)throw Error('WARMUP_200');
 const {result,metrics:m}=candidates(closed,step),bar=closed.at(-1),at=bar.time+step;
 return result.map(x=>{
  const detected=x.side!=='WAIT',sign=x.side==='LONG'?1:-1,entry=bar.close;
  const distance=detected?Math.max(1.5*m.atr,sign*(entry-x.anchor)+.25*m.atr):null;
  const stop=detected?entry-sign*distance:null,target=detected?entry+sign*3*distance:null;
  const fees=detected?cost(entry,stop,target,x.side,spread,multiplier):null;
  const geometry=detected&&[entry,stop,target,fees.net_rr].every(finite)&&Math.min(entry,stop,target)>0&&fees.net_rr>=1.5;
  return {...x,id:VERSION+':'+x.strategy+':'+step+':'+at,version:VERSION,name:names[x.strategy],setup:x.side,
   state:!detected?'WAIT':geometry?x.side:'REJECTED',edge:'UNVALIDATED',edge_summary:'NO_VALIDATED_EDGE',research:true,
   formed_at:at,valid_until:at+step,entry:detected?entry:null,zone:detected?{low:entry-.25*m.atr,high:entry+.25*m.atr}:null,
   stop,target,net_rr:fees?.net_rr??null,costs:fees,
   rejection:detected&&!geometry?['INVALID_GEOMETRY_OR_NET_RR_BELOW_1_5']:[],
   cancel:'Истечение свечного срока, выход за зону входа, пересечение SL/TP или недостоверные данные.'};
 });
}
function analyze(snapshot,now,enabled=Object.keys(names)){
 const rows=[];
 for(const tf of ['15m','1h','4h']){
  try{
   const live=A.chartQuote(snapshot,tf,now).live;
   for(const x of evaluate(snapshot.windows?.[tf]?.bars,A.STEPS[tf],now)){
    if(!enabled.includes(x.strategy))continue;
    const reasons=[...x.rejection];let rr=x.net_rr;
    if(x.setup!=='WAIT'){
     if(!live)reasons.push('STALE_OR_UNVERIFIED_MARKET');
     else{
      const q=snapshot.quote,entry=x.setup==='LONG'?q.ask:q.bid;
      if(now>=x.valid_until)reasons.push('EXPIRED');
      if(entry<x.zone.low||entry>x.zone.high)reasons.push('OUTSIDE_ENTRY_ZONE');
      const geometry=x.setup==='LONG'?x.stop<entry&&entry<x.target:x.target<entry&&entry<x.stop;
      // entry is already the executable ask/bid; spread is paid again only on exit.
      const fees=cost(entry,x.stop,x.target,x.setup,q.ask-q.bid);
      rr=fees.net_rr;if(!geometry||!finite(rr)||rr<1.5)reasons.push('LIVE_NET_RR_BELOW_1_5');
     }
    }
    rows.push({...x,tf,fresh:live,quote_age:snapshot?.quote?now-snapshot.quote.time:null,net_rr:rr,
     state:x.setup==='WAIT'?'WAIT':reasons.length?'REJECTED':x.setup,rejection:reasons,detected_at:now});
   }
  }catch(e){for(const strategy of enabled)if(names[strategy])rows.push({strategy,name:names[strategy],tf,state:'REJECTED',setup:null,edge:'UNVALIDATED',edge_summary:'NO_VALIDATED_EDGE',fresh:false,reasons:['Анализ заблокирован: '+e.message],rejection:['DATA_UNAVAILABLE'],technical_strength:null});}
 }
 return rows;
}
const api={VERSION,names,cost,candidates,evaluate,analyze};root.AuraManualStrategies=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);

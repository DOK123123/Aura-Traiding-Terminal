/* Manual-only, causal provisional analysis. No network, storage or order authority. */
(function(root){'use strict';
 const STEPS={'1m':60,'5m':300,'15m':900,'1h':3600,'4h':14400},VERSION='AURA_LIVE_MANUAL_1';
 const finite=n=>typeof n==='number'&&Number.isFinite(n);
 function emaSeries(v,n){if(v.length<n)return [];let x=v.slice(0,n).reduce((a,b)=>a+b,0)/n;const out=[x];for(const p of v.slice(n)){x+=2/(n+1)*(p-x);out.push(x);}return out;}
 const ema=(v,n)=>emaSeries(v,n).at(-1);
 function rsi(v,n=14){if(v.length<=n)return null;const d=v.slice(1).map((x,i)=>x-v[i]);let g=d.slice(0,n).reduce((a,b)=>a+Math.max(0,b),0)/n,l=d.slice(0,n).reduce((a,b)=>a+Math.max(0,-b),0)/n;for(const x of d.slice(n)){g=(g*(n-1)+Math.max(0,x))/n;l=(l*(n-1)+Math.max(0,-x))/n;}return l===0?(g===0?50:100):100-100/(1+g/l);}
 function atr(b,n=14){const t=b.slice(1).map((x,i)=>Math.max(x.high-x.low,Math.abs(x.high-b[i].close),Math.abs(x.low-b[i].close)));if(t.length<n)return null;let x=t.slice(0,n).reduce((a,b)=>a+b,0)/n;for(const p of t.slice(n))x=(x*(n-1)+p)/n;return x;}
 function metrics(b){const c=b.map(x=>x.close),e20=ema(c,20),e50=ema(c,50),a=atr(b),fast=emaSeries(c,12).slice(14),slow=emaSeries(c,26),m=slow.map((x,i)=>fast[i]-x),signal=ema(m,9),line=m.at(-1);return {ema20:e20,ema50:e50,rsi:rsi(c),atr:a,macd:line,macd_signal:signal,histogram:line-signal,trend:e20-e50>.1*a?'LONG':e50-e20>.1*a?'SHORT':'NEUTRAL',close:c.at(-1)};}
 function swings(b,step){const out=[];for(let i=2;i<b.length-2;i++){const n=[...b.slice(i-2,i),...b.slice(i+1,i+3)];for(const [kind,k,cmp]of [['HIGH','high',(a,b)=>a>b],['LOW','low',(a,b)=>a<b]])if(n.every(x=>cmp(b[i][k],x[k])))out.push({kind,price:b[i][k],time:b[i].time,index:i,confirmed_at:b[i+2].time+step});}return out;}
 function context(b,step){const p=swings(b,step),hi=p.filter(x=>x.kind==='HIGH'),lo=p.filter(x=>x.kind==='LOW'),c=b.map(x=>x.close);let structure='UNCONFIRMED';if(hi.length>=2&&lo.length>=2){const h=hi.at(-1).price-hi.at(-2).price,l=lo.at(-1).price-lo.at(-2).price;structure=h>0&&l>0?'HH_HL':h<0&&l<0?'LH_LL':'RANGE';}const divergence=[];for(const [points,side]of [[lo,'LONG'],[hi,'SHORT']]){if(points.length<2)continue;const [a,z]=points.slice(-2),ra=rsi(c.slice(0,a.index+1)),rz=rsi(c.slice(0,z.index+1));if(ra===null||rz===null||z.index-a.index>50||b.length-1-z.index>10)continue;if(side==='LONG'?z.price<a.price&&rz>ra:z.price>a.price&&rz<ra)divergence.push({side,confirmed_at:z.confirmed_at});}return {structure,divergence,swings:p.slice(-12)};}
 function windowCheck(b,step,now){if(!Array.isArray(b)||b.length<101||b.length>301)throw Error('INCOMPLETE_HISTORY');for(let i=0;i<b.length;i++){const x=b[i];if(!Number.isInteger(x.time)||x.time%step||x.time>now||!['open','high','low','close','volume'].every(k=>finite(x[k]))||Math.min(x.open,x.high,x.low,x.close)<=0||x.volume<0||x.low>Math.min(x.open,x.close)||x.high<Math.max(x.open,x.close)||i&&x.time-b[i-1].time!==step)throw Error('INVALID_HISTORY');}const closed=b.filter(x=>x.time+step<=now);if(closed.at(-1)?.time+step!==Math.floor(now/step)*step)throw Error('STALE_HISTORY');return closed;}
 function quoteFresh(q,now){return q&&q.source==='BITGET_USDT_FUTURES_BTCUSDT'&&[q.bid,q.ask,q.last,q.time,q.received_at].every(finite)&&q.bid>0&&q.ask>=q.bid&&(q.ask-q.bid)/q.bid<=.005&&q.last>=q.bid*.99&&q.last<=q.ask*1.01&&now-q.time>=0&&now-q.time<=5&&now-q.received_at>=0&&now-q.received_at<=5;}
 function risk(entry,stop,target,long,spread=0){const slip=.0005,fee=.001,sign=long?1:-1,e=entry*(1+sign*slip),s=stop*(1-sign*slip)-sign*spread/2,t=target*(1-sign*slip)-sign*spread/2,loss=sign*(e-s)+(e+s)*fee,gain=sign*(t-e)-(e+t)*fee;return {net_rr:Math.max(0,gain)/loss,gross_rr:Math.abs(target-entry)/Math.abs(entry-stop),fee_per_side:fee,slippage_per_side:slip,spread,funding:'NOT_INCLUDED'};}
 function analyze(snapshot,now){const out={version:VERSION,state:'WAIT',preliminary:true,scenario:null,frames:{},reasons:[],evidence:[],generated_at:now,valid_until:now,read_only:true};
 try{
  if(!finite(now)||snapshot.status!=='LIVE'||!quoteFresh(snapshot.quote,now))throw Error('STALE_MARKET');
  const closed={};for(const [tf,step]of Object.entries(STEPS)){const w=snapshot.windows?.[tf];if(!finite(w?.received_at)||!finite(w?.event_at)||now-w.received_at<0||now-w.received_at>10||now-w.event_at<0||now-w.event_at>10)throw Error('STALE_STREAM_'+tf);closed[tf]=windowCheck(w.bars,step,now);const current=w.bars.at(-1);if(current.time!==Math.floor(now/step)*step)throw Error('FORMING_CANDLE_MISSING_'+tf);out.frames[tf]={confirmed:metrics(closed[tf]),preliminary:metrics(w.bars),context:context(closed[tf],step),last_closed_at:closed[tf].at(-1).time+step};}
  out.valid_until=Math.min(now+2,snapshot.quote.time+5,...Object.values(snapshot.windows).map(w=>w.event_at+10));
  const f=out.frames,side=f['1h'].confirmed.trend,long=side==='LONG',live=f['5m'].preliminary,bars=snapshot.windows['5m'].bars,last=bars.at(-1),previous=closed['5m'].at(-1),av=live.atr;
  for(const [tf,x]of Object.entries(f)){for(const [name,bias,stage]of [['EMA20/50',x.confirmed.trend,'CONFIRMED'],['MACD',x.preliminary.histogram>0?'LONG':x.preliminary.histogram<0?'SHORT':'NEUTRAL','PRELIMINARY'],['Структура',x.context.structure==='HH_HL'?'LONG':x.context.structure==='LH_LL'?'SHORT':'NEUTRAL','CONFIRMED'],...x.context.divergence.map(p=>['RSI divergence',p.side,'CONFIRMED'])])out.evidence.push({tf,name,bias,stage,relation:side==='NEUTRAL'||bias==='NEUTRAL'?'NEUTRAL':bias===side?'SUPPORTS':'CONFLICTS'});}
  out.levels={support:Math.min(...closed['5m'].slice(-20).map(x=>x.low)),resistance:Math.max(...closed['5m'].slice(-20).map(x=>x.high))};
  if(side==='NEUTRAL'||['5m','15m'].some(tf=>f[tf].confirmed.trend!==side))throw Error('CLOSED_TREND_NOT_ALIGNED');
  if(![side,'NEUTRAL'].includes(f['4h'].confirmed.trend))throw Error('CONFLICTING_4H');
  if(live.trend!==side||!(long?52<=live.rsi&&live.rsi<=68:32<=live.rsi&&live.rsi<=48))throw Error('LIVE_MOMENTUM_NOT_CONFIRMED');
  const h=closed['15m'].slice(-60),lows=h.map(x=>x.low),highs=h.map(x=>x.high),low=Math.min(...lows),high=Math.max(...highs),li=lows.indexOf(low),hi=highs.indexOf(high);
  if(high<=low||(long?li>=hi:hi>=li))throw Error('NO_PAST_ORDERED_SWING');
  const fib=r=>long?high-(high-low)*r:low+(high-low)*r;out.fibonacci={low,high,levels:[.236,.382,.5,.618,.786].map(r=>({ratio:r,price:fib(r)}))};
  const lower=Math.max(Math.min(fib(.382),fib(.618)),live.ema20-.5*av),upper=Math.min(Math.max(fib(.382),fib(.618)),live.ema20+.5*av),entry=long?snapshot.quote.ask:snapshot.quote.bid;
  if(lower>=upper||entry<lower-.25*av||entry>upper+.25*av)throw Error('NO_LIVE_ENTRY_CONFLUENCE');
  const recovery=long?last.close>last.open&&last.close>previous.close+.05*av&&last.low<=upper:last.close<last.open&&last.close<previous.close-.05*av&&last.high>=lower;
  if(!recovery)throw Error('PROVISIONAL_CANDLE_NOT_CONFIRMED');
  // Compare partial volume with a historical *partial-time* expectation; never call final volume confirmed.
  const mean=closed['5m'].slice(-20).reduce((s,b)=>s+b.volume,0)/20,fraction=Math.max(.1,Math.min(1,(now-last.time)/300)),ratio=mean>0?last.volume/(mean*fraction):null;out.partial_volume_ratio=ratio;
  if(ratio===null||ratio<1)throw Error('PARTIAL_VOLUME_NOT_SUPPORTING');
  if(long?live.histogram<=0:live.histogram>=0)throw Error('LIVE_MACD_CONFLICT');
  const recent=bars.slice(-3),stop=long?Math.min(...recent.map(x=>x.low-.25*av),lower-1.5*av):Math.max(...recent.map(x=>x.high+.25*av),upper+1.5*av),distance=Math.abs(entry-stop),target=long?Math.min(high,entry+2.5*distance):Math.max(low,entry-2.5*distance),cost=risk(entry,stop,target,long,snapshot.quote.ask-snapshot.quote.bid);
  if(!(long?stop<entry&&target>entry:stop>entry&&target<entry)||!finite(cost.net_rr)||cost.net_rr<1.5)throw Error('INSUFFICIENT_RR_AFTER_COSTS');
  out.state=side;out.scenario={reference_entry:entry,entry_zone:{low:lower,high:upper},stop_loss:stop,take_profit:target,...cost};out.reasons=['CLOSED_TREND_ALIGNED','LIVE_CONFLUENCE_PRELIMINARY','LIVE_CANDLE_PRELIMINARY','PARTIAL_VOLUME_PRELIMINARY'];
 }catch(e){out.state='WAIT';out.scenario=null;out.reasons=[e.message||'INVALID_DATA'];}return out;
 }
 class History{constructor(limit=100){this.limit=limit;this.items=[];}add(v){const signature=JSON.stringify([v.state,v.reasons]);if(this.items.at(-1)?.signature!==signature)this.items.push({signature,at:v.generated_at,state:v.state,reasons:[...v.reasons]});this.items=this.items.slice(-this.limit);return this.items;}}
 const api={STEPS,VERSION,ema,rsi,atr,metrics,swings,context,windowCheck,quoteFresh,risk,analyze,History};root.AuraManualLiveAnalysis=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);

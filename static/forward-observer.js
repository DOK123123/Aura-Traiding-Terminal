/* Browser-local read-only observer. Never fetches, submits or restores orders. */
(function(root){'use strict';
const A=root.AuraManualLiveAnalysis||(typeof require==='function'?require('./manual-live-analysis.js'):null);
const VERSION='FORWARD_OBSERVER_1',KEY='aura.forward.observer.v1';
class Observer{
 constructor(storage=null){this.storage=storage;this.items=[];this.error=null;this.last=null;try{const data=JSON.parse(storage?.getItem(KEY)||'null');if(data?.version===VERSION&&Array.isArray(data.items))this.items=data.items.filter(x=>typeof x.id==='string'&&['LONG','SHORT'].includes(x.side)&&['entry','stop','target'].every(k=>Number.isFinite(x[k])&&x[k]>0)&&['OPEN','SL','TP','TIMEOUT','REJECTED','EXPIRED','UNOBSERVED'].includes(x.outcome)&&Number.isFinite(x.detected_at)&&(x.outcome!=='OPEN'||['fill','last_observed','last_quote_at','deadline'].every(k=>Number.isFinite(x[k])))).slice(-500);}catch{this.error='Журнал не восстановлен';}}
 save(){try{this.storage?.setItem(KEY,JSON.stringify({version:VERSION,items:this.items}));}catch{this.error='Журнал не сохранён: хранилище недоступно';}}
 update(snapshot,rows,now){
  const fresh=snapshot?.status==='LIVE'&&A.quoteFresh(snapshot.quote,now),q=snapshot?.quote;
  for(const x of this.items.filter(x=>x.outcome==='OPEN')){
   // A sleep/restart/feed gap cannot be reconstructed from a later tick.
   if(!fresh||now<x.last_observed||now-x.last_observed>10){x.outcome='UNOBSERVED';x.finished_at=now;x.reason='Разрыв наблюдения: путь SL/TP неизвестен';continue;}
   if(q.time<=x.last_quote_at)continue;
   const long=x.side==='LONG',exit=long?q.bid:q.ask,stop=long?exit<=x.stop:exit>=x.stop,target=long?exit>=x.target:exit<=x.target;
   x.last_observed=now;x.last_quote_at=q.time;
   if(stop||target||now>=x.deadline){
    x.outcome=stop?'SL':target?'TP':'TIMEOUT';x.finished_at=now;
    x.exit=exit*(1+(long?-1:1)*.0005);
    const sign=long?1:-1;x.pnl_fraction=(sign*(x.exit-x.fill)-.001*(x.fill+x.exit))/x.fill;
   }
  }
  for(const s of rows){
   if(!s.id||!['LONG','SHORT'].includes(s.setup)||this.items.some(x=>x.id===s.id))continue;
   const executable=fresh&&['LONG','SHORT'].includes(s.state);
   const x={id:s.id,version:s.version,strategy:s.strategy,tf:s.tf,side:s.setup,state:s.state,edge:s.edge,formed_at:s.formed_at,detected_at:now,entry:s.entry,zone:s.zone,stop:s.stop,target:s.target,net_rr:s.net_rr,reasons:[...s.reasons],rejection:[...s.rejection],cancel:s.cancel,
    outcome:executable?'OPEN':s.rejection.includes('EXPIRED')?'EXPIRED':'REJECTED',pnl_fraction:null};
   if(executable){x.bid=q.bid;x.ask=q.ask;x.quote_at=q.time;x.fill=(x.side==='LONG'?q.ask:q.bid)*(1+(x.side==='LONG'?1:-1)*.0005);x.deadline=now+16*A.STEPS[s.tf];x.last_observed=now;x.last_quote_at=q.time;}
   this.items.push(x);
  }
  this.items=this.items.slice(-500);this.last=now;this.save();return this.items;
 }
}
const api={Observer,VERSION,KEY};root.AuraForwardObserver=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);

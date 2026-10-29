/* Offline manual-intent execution model, no exchange/storage/API imports. */
'use strict';
class Model{
 constructor(protocol,cost=1){this.protocol=protocol;this.cost=cost;this.cash=10000;this.position=null;this.pending=null;this.used=new Set();this.trades=[];this.equity=[];this.rejections={};this.day=null;this.dayStart=10000;}
 reject(code){this.rejections[code]=(this.rejections[code]||0)+1;}
 fill(price,long,entry){return price*(1+(long?1:-1)*(entry?1:-1)*(this.protocol.costs.slippage_per_side+this.protocol.costs.spread_bps/20000)*this.cost);}
 close(price,time,reason){const p=this.position,x=this.fill(price,p.side==='LONG',false),gross=(x-p.entry)*p.quantity*(p.side==='LONG'?1:-1),exitFee=x*p.quantity*this.protocol.costs.fee_per_side*this.cost,net=gross-p.entry_fee-exitFee;this.cash+=gross-exitFee;this.trades.push({...p,exit:x,closed_at:time,reason,gross,fees:p.entry_fee+exitFee,net});this.position=null;}
 atOpen(b){
  const day=Math.floor(b.time/86400);if(this.day!==day){this.day=day;const p=this.position;this.dayStart=this.cash+(p?(b.open-p.entry)*p.quantity*(p.side==='LONG'?1:-1):0);}
  if(this.position){const p=this.position,long=p.side==='LONG';if(long?b.open<=p.stop:b.open>=p.stop)this.close(b.open,b.time,'STOP_GAP');else if(long?b.open>=p.target:b.open<=p.target)this.close(p.target,b.time,'TAKE_PROFIT_GAP_CAPPED');}
  if(this.position||!this.pending||b.time<this.pending.available_at+this.protocol.sample.execution_delay_min_seconds)return;
  const p=this.pending;this.pending=null;
  if(b.time-p.available_at>120){this.reject('INTENT_EXPIRED');return;}
  if(b.volume<=0){this.reject('NO_PRINTS');return;}
  const long=p.side==='LONG',e=this.fill(b.open,long,true),stop=p.stop_loss,target=p.take_profit,s=this.fill(stop,long,false),t=this.fill(target,long,false),sign=long?1:-1,fee=this.protocol.costs.fee_per_side*this.cost,loss=sign*(e-s)+(e+s)*fee,reward=sign*(t-e)-(e+t)*fee;
  if(!(p.entry_zone.low<=e&&e<=p.entry_zone.high)){this.reject('ENTRY_OUTSIDE_ZONE');return;}
  if(!(long?stop<e&&e<target:target<e&&e<stop)||loss<=0||reward/loss<(p.min_net_rr||1.5)){this.reject('GEOMETRY_OR_RR_AFTER_COSTS');return;}
  const budget=Math.min(this.cash*.005,Math.max(0,this.dayStart*.02+this.cash-this.dayStart),Math.max(0,this.cash-9000)),q=Math.floor(Math.min(2000/e,(this.cash/(1+fee))/e,budget/loss)*10000)/10000;
  if(q<.0001||q*e<5){this.reject('RISK_OR_MIN_SIZE');return;}
  const entry_fee=e*q*fee;this.cash-=entry_fee;this.position={id:p.id,side:p.side,entry:e,quantity:q,stop,target,entry_fee,opened_at:b.time,regime:p.regime};
 }
 signal(value,time,id,regime){
  if(value.state==='WAIT'||!value.scenario){if(this.pending){this.reject('PRELIMINARY_WITHDRAWN');this.pending=null;}return;}
  if(this.pending&&this.pending.side!==value.state){this.reject('DIRECTION_CHANGED');this.pending=null;}
  if(this.position||this.pending||this.used.has(id))return;
  this.used.add(id);this.pending={...value.scenario,side:value.state,available_at:time,id,regime};
 }
 atClose(b){
  const p=this.position;if(p&&b.volume>0){const long=p.side==='LONG',stop=long?b.low<=p.stop:b.high>=p.stop,target=long?b.high>=p.target:b.low<=p.target;if(stop)this.close(long?Math.min(b.open,p.stop):Math.max(b.open,p.stop),b.time+60,'STOP_LOSS');else if(target)this.close(p.target,b.time+60,'TAKE_PROFIT');}
  const x=this.position;this.equity.push({time:b.time+60,equity:this.cash+(x?(b.close-x.entry)*x.quantity*(x.side==='LONG'?1:-1)-this.fill(b.close,x.side==='LONG',false)*x.quantity*this.protocol.costs.fee_per_side*this.cost:0)});
 }
 finish(b){if(this.position)this.close(b.close,b.time+60,'SEGMENT_END_ESTIMATE');this.equity.push({time:b.time+60,equity:this.cash});}
 metrics(){let peak=10000,dd=0;for(const p of this.equity){peak=Math.max(peak,p.equity);dd=Math.max(dd,(peak-p.equity)/peak*100);}const t=this.trades,n=t.length,profit=t.reduce((s,t)=>s+Math.max(0,t.net),0),loss=-t.reduce((s,t)=>s+Math.min(0,t.net),0),fees=t.reduce((s,t)=>s+t.fees,0);return {trades:n,long:t.filter(t=>t.side==='LONG').length,short:t.filter(t=>t.side==='SHORT').length,net_pnl:this.cash-10000,return_pct:(this.cash/10000-1)*100,profit_factor:loss?profit/loss:null,expectancy:n?(this.cash-10000)/n:null,win_rate_pct:n?t.filter(t=>t.net>0).length/n*100:null,max_drawdown_pct:dd,fees,average_duration_minutes:n?t.reduce((s,t)=>s+(t.closed_at-t.opened_at)/60,0)/n:null,rejections:this.rejections};}
}
module.exports={Model};

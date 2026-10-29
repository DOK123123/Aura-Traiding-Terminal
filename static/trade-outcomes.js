/* Pure research ledger. Never sends orders, changes strategy decisions or reads future bars. */
(function(root){'use strict';
const DEFAULTS=Object.freeze({entry_bars:1,hold_bars:96,full_spread_bps:2,slippage_bps_per_side:5,fee_bps_per_side:10,quantity_btc:1});
const resolved=t=>['TP','SL','TIMEOUT'].includes(t.outcome)&&t.entered&&Number.isFinite(t.pnl_usdt);
function parameters(input={}){
 const p={...DEFAULTS,...input};
 if(Object.keys(p).some(k=>!Object.hasOwn(DEFAULTS,k))||p.entry_bars!==1||!Number.isInteger(p.hold_bars)||p.hold_bars<1||p.hold_bars>1000||p.quantity_btc!==1||!['full_spread_bps','slippage_bps_per_side','fee_bps_per_side'].every(k=>Number.isFinite(p[k])&&p[k]>=0&&p[k]<=100))throw Error('INVALID_OUTCOME_PARAMETERS');
 return Object.freeze(p);
}
class Analyzer{
 constructor(step,params={}){if(![900,3600,14400].includes(step))throw Error('INVALID_OUTCOME_STEP');this.step=step;this.params=parameters(params);this.reset();}
 reset(){this.trades=[];this.ids=new Set();this.active=[];this.lastTime=null;this.complete=false;}
 register(s){
  if(!['LONG','SHORT'].includes(s.state))return;
  const sign=s.state==='LONG'?1:-1,key=[s.strategy,s.state,s.tf,s.id].join('|');
  if(this.ids.has(key))return;
  if(!s.id||!s.strategy||!s.tf||!Number.isInteger(s.formed_at)||s.formed_at%this.step||!Number.isInteger(s.valid_until)||s.valid_until!==s.formed_at+this.step||!['entry','stop','target'].every(k=>Number.isFinite(s[k])&&s[k]>0)||sign*(s.entry-s.stop)<=0||sign*(s.target-s.entry)<=0||this.complete||this.lastTime===null||s.formed_at!==this.lastTime+this.step)throw Error('INVALID_OR_NONCAUSAL_OUTCOME_SIGNAL');
  this.ids.add(key);const t={key,id:s.id,strategy:s.strategy,direction:s.state,tf:s.tf,signal_time:s.formed_at,entry:s.entry,sl:s.stop,tp:s.target,entry_deadline:s.valid_until,reasons:[...(s.reasons||[])],cancel:s.cancel,edge:'UNVALIDATED',outcome:'PENDING',entered:false,ambiguous:false,entry_time:null,exit_time:null,entry_fill:null,exit_fill:null,fees_usdt:null,pnl_usdt:null,r:null,note:'AWAITING_NEXT_CANDLE',bars_held:0};this.trades.push(t);this.active.push(t);
 }
 finish(t,outcome,note){t.outcome=outcome;t.note=note;}
 close(t,outcome,price,time,note){
  const p=this.params,sign=t.direction==='LONG'?1:-1;
  t.exit_fill=price*(1-sign*p.slippage_bps_per_side/1e4);t.exit_time=time;
  t.fees_usdt=(t.entry_fill+t.exit_fill)*p.fee_bps_per_side/1e4;
  t.pnl_usdt=sign*(t.exit_fill-t.entry_fill)-t.fees_usdt;
  // R denominator is the predeclared price risk per 1 BTC, without retrospective resizing.
  t.r=t.pnl_usdt/Math.abs(t.entry-t.sl);this.finish(t,outcome,note);
 }
 advance(b){
  if(this.complete||!Number.isInteger(b.time)||b.time%this.step||this.lastTime!==null&&b.time!==this.lastTime+this.step||!['open','high','low','close'].every(k=>Number.isFinite(b[k])&&b[k]>0)||b.high<Math.max(b.open,b.close)||b.low>Math.min(b.open,b.close))throw Error('INVALID_OR_NONCHRONOLOGICAL_OUTCOME_BAR');
  this.lastTime=b.time;const p=this.params,half=p.full_spread_bps/2e4;
  for(const t of this.active){
   if(b.time<t.signal_time)continue;
   const long=t.direction==='LONG',sign=long?1:-1;
   // Modeled executable ask for buy entries, bid for sells; quotes are NOT historical Bid/Ask.
   const q=1+sign*half,exitQ=1-sign*half;
   let atOpen=false,enteredHere=false;
   if(!t.entered){
    if(b.time>=t.entry_deadline){this.finish(t,'TIMEOUT','ENTRY_EXPIRED_NO_FILL');continue;}
    const open=b.open*q,stopBeyond=long?open<=t.sl:open>=t.sl;
    atOpen=long?open<=t.entry:open>=t.entry;
    const touch=atOpen||(long?b.low*q<=t.entry:b.high*q>=t.entry);
    if(!touch){if(b.time+this.step>=t.entry_deadline)this.finish(t,'TIMEOUT','ENTRY_NOT_REACHED');continue;}
    if(stopBeyond){t.ambiguous=true;this.finish(t,'UNKNOWN','GAP_BEYOND_SL_BEFORE_CONFIRMED_ENTRY');continue;}
    t.entered=true;t.entry_time=b.time;t.entry_fill=t.entry*(1+sign*p.slippage_bps_per_side/1e4);t.outcome='OPEN';t.note='MODELED_ENTRY_TOUCH';enteredHere=true;
   }
   t.bars_held++;const open=b.open*exitQ,low=b.low*exitQ,high=b.high*exitQ;
   const sl=long?low<=t.sl:high>=t.sl,tp=long?high>=t.tp:low<=t.tp;
   // Open gaps have known priority for an already open position; favorable TP fills capped.
   if((!enteredHere||atOpen)&&(long?open<=t.sl:open>=t.sl)){this.close(t,'SL',open,b.time,'ADVERSE_STOP_GAP');continue;}
   if(!enteredHere&&(long?open>=t.tp:open<=t.tp)){this.close(t,'TP',t.tp,b.time,'TARGET_GAP_CAPPED');continue;}
   if(sl){t.ambiguous=tp||enteredHere&&!atOpen;this.close(t,'SL',t.sl,b.time,tp?'BOTH_TOUCHED_SL_FIRST':t.ambiguous?'ENTRY_STOP_ORDER_CONSERVATIVE':'STOP_TOUCHED');continue;}
   if(tp){
    if(enteredHere&&!atOpen){t.ambiguous=true;this.finish(t,'UNKNOWN','ENTRY_TP_SEQUENCE_UNKNOWN');}
    else this.close(t,'TP',t.tp,b.time,'TARGET_TOUCHED');
    continue;
   }
   if(t.bars_held>=p.hold_bars)this.close(t,'TIMEOUT',b.close*exitQ,b.time,'HOLD_LIMIT_CLOSE');
  }
  this.active=this.active.filter(t=>['OPEN','PENDING'].includes(t.outcome));
 }
 finalize(){this.complete=true;for(const t of this.active)this.finish(t,'UNKNOWN',t.entered?'END_OF_DATA_OPEN':'END_OF_DATA_BEFORE_ENTRY');this.active=[];}
 report(){const trades=this.trades.map(t=>({...t,reasons:[...t.reasons]}));return {version:'HISTORICAL_TRADE_OUTCOMES_1',parameters:{...this.params,entry_model:'NEXT_BAR_REFERENCE_TOUCH_ADVERSE_SLIPPAGE_NO_FAVORABLE_IMPROVEMENT',exit_model:'EXECUTABLE_QUOTE_TOUCH_ADVERSE_SL_GAP_TP_CAPPED',intrabar_rule:'SL_FIRST_BOTH;UNKNOWN_ENTRY_TP_SEQUENCE',timestamp_resolution:'CANDLE_OPEN_NOT_EXACT_FILL',risk_R:'ABS_PLANNED_ENTRY_MINUS_SL',portfolio_model:'NONE_INDEPENDENT_1_BTC_HYPOTHESES',funding:'NOT_MODELED',historical_bid_ask:false},complete:this.complete,edge:'UNVALIDATED',validation:'NO_VALIDATED_EDGE',trades,statistics:statistics(trades)};}
}
function metrics(trades){
 const closed=trades.filter(resolved).sort((a,b)=>a.exit_time-b.exit_time||a.key.localeCompare(b.key)),wins=closed.filter(t=>t.pnl_usdt>0),losses=closed.filter(t=>t.pnl_usdt<0),sum=(a,k)=>a.reduce((s,t)=>s+t[k],0),profit=sum(wins,'pnl_usdt'),loss=-sum(losses,'pnl_usdt');
 let cumulative=0,peak=0,maxDD=0,cumulativeR=0,peakR=0,maxDDR=0;const curve=[];
 for(const t of closed){cumulative+=t.pnl_usdt;cumulativeR+=t.r;peak=Math.max(peak,cumulative);peakR=Math.max(peakR,cumulativeR);maxDD=Math.max(maxDD,peak-cumulative);maxDDR=Math.max(maxDDR,peakR-cumulativeR);curve.push({time:t.exit_time,cumulative_usdt:cumulative,cumulative_R:cumulativeR});}
 return {signals:trades.length,entered:trades.filter(t=>t.entered).length,resolved:closed.length,unknown:trades.filter(t=>t.outcome==='UNKNOWN').length,pending:trades.filter(t=>['PENDING','OPEN'].includes(t.outcome)).length,not_filled:trades.filter(t=>!t.entered&&t.outcome==='TIMEOUT').length,ambiguous:trades.filter(t=>t.ambiguous).length,win_rate:closed.length?wins.length/closed.length:null,profit_factor:loss?profit/loss:null,profit_factor_note:loss?'DEFINED':'NO_LOSSES_OR_NO_CLOSED_TRADES',average_profit_usdt:wins.length?profit/wins.length:null,average_loss_usdt:losses.length?-loss/losses.length:null,expectancy_R:closed.length?sum(closed,'r')/closed.length:null,pnl_usdt:closed.length?sum(closed,'pnl_usdt'):null,max_drawdown_usdt:closed.length?maxDD:null,max_drawdown_R:closed.length?maxDDR:null,portfolio_return:null,curve};
}
function statistics(trades){
 const groups=Object.fromEntries(['TREND_PULLBACK','BREAKOUT_RETEST','SR_REVERSAL'].flatMap(strategy=>['LONG','SHORT'].map(side=>[strategy+'|'+side,[]])));for(const t of trades){const key=t.strategy+'|'+t.direction;(groups[key]??=[]).push(t);}
 const monthly={};for(const t of trades){const key=new Date(t.signal_time*1000).toISOString().slice(0,7)+'|'+t.strategy+'|'+t.direction;(monthly[key]??=[]).push(t);}
 return {grouping:'STRATEGY_DIRECTION;MONTH_IS_SIGNAL_COHORT_UTC',groups:Object.fromEntries(Object.entries(groups).map(([k,v])=>[k,metrics(v)])),months:Object.fromEntries(Object.entries(monthly).map(([k,v])=>[k,metrics(v)]))};
}
const FIELDS=['id','strategy','tf','direction','signal_time','entry','sl','tp','outcome','entered','entry_time','exit_time','entry_fill','exit_fill','fees_usdt','pnl_usdt','r','ambiguous','note','edge'];
function csv(report){
 const cell=v=>{let s=typeof v==='object'&&v!==null?JSON.stringify(v):String(v??'');if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
 const columns=['record_type',...FIELDS,'group','metadata'];
 const row=(kind,t={},group='',metadata='')=>[kind,...FIELDS.map(k=>t[k]??''),group,metadata].map(cell).join(',');
 const rows=[columns.join(','),row('MODEL',{},'',{...report,trades:undefined,statistics:undefined})];
 for(const t of report.trades)rows.push(row('TRADE',t));
 for(const grouping of ['groups','months'])for(const [key,m]of Object.entries(report.statistics[grouping])){const {curve,...metrics}=m;rows.push(row(grouping==='groups'?'STATISTICS':'MONTH',{},key,metrics));if(grouping==='groups')for(const point of curve)rows.push(row('CURVE',{},key,point));}
 return '\uFEFF'+rows.join('\r\n');
}
const api={Analyzer,DEFAULTS,metrics,statistics,csv};root.AuraTradeOutcomes=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);

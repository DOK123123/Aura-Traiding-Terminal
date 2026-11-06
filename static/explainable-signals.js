/* Presentation of server-owned causal evidence. GET data arrives from HomeFeed.
 * No order, virtual trade, ledger write, clipboard or account authority. */
(function(root){'use strict';
const VERSION='AURA5_EXPLAINABLE_V1',SOURCE='BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2';
const FRAMES={'5m':300,'15m':900,'1h':3600,'4h':14400};
const NAMES={TREND_PULLBACK:'Trend Pullback',BREAKOUT_RETEST:'Breakout + Retest',MOMENTUM_DIVERGENCE:'Momentum Divergence'};
const LABELS={EMA_TREND:'Тренд EMA20/50',TREND_STRUCTURE:'Структура тренда',PULLBACK:'Откат к EMA',RSI:'RSI14',
 PRIOR_LEVEL_BREAK:'Пробой известного уровня',LEVEL_HELD:'Удержание уровня',SEPARATE_RETEST:'Отдельный ретест',BREAK_VOLUME:'Объём пробоя',
 CONFIRMED_PIVOTS:'Подтверждённые экстремумы',PRICE_DIVERGENCE:'Новый ценовой экстремум',RSI_DIVERGENCE:'Дивергенция RSI',
 MACD_DIVERGENCE:'Дивергенция MACD',MOMENTUM_TURN:'Разворот импульса MACD',CLOSED_CANDLE_CONFIRMATION:'Подтверждение закрытой свечой',
 TARGET_TOO_FAR_FOR_HORIZON:'Цель слишком далеко относительно ATR и срока удержания',
 STOP_WIDER_THAN_3_ATR:'Структурный стоп шире 3 ATR',ENTRY_IN_OPPOSING_ZONE:'Вход внутри встречной зоны',
 NET_RR_BELOW_1_5_OR_INVALID_GEOMETRY:'Net R/R ниже 1.5 или некорректные уровни',NO_KNOWN_OPPOSING_PIVOT_TARGET:'Нет известного встречного экстремума для TP',
 NO_STRUCTURAL_INVALIDATION_BEHIND_ENTRY:'Нет структурного уровня отмены за Entry',OUTSIDE_CLOSED_SIGNAL_ENTRY_ZONE:'Котировка или модельное исполнение вышли из зоны входа',
 STALE_OR_UNVERIFIED_BITGET_QUOTE:'Нет свежих проверенных Bid/Ask Bitget',INCOMPLETE_OR_STALE_CLOSED_HISTORY:'Недостаточная или устаревшая история закрытых свечей',
 OBSERVER_STOPPED_OR_NO_CAPTURED_HISTORY:'Наблюдатель остановлен или история ещё не получена',INVALID_OHLCV_OR_GAP:'Некорректные свечи или разрыв истории',
 INDICATOR_WARMUP_OR_ZERO_ATR:'Индикаторы не рассчитаны или ATR равен нулю',CAPTURED_INPUT_UNAVAILABLE:'Сохранённый набор данных недоступен'};
function candidateRows(data){return Array.isArray(data?.explainable_candidates)?data.explainable_candidates.filter(c=>c&&typeof c==='object'&&!Array.isArray(c)):[];}
function evidence(c){return !!(c&&typeof c==='object'&&Array.isArray(c.checks)&&c.checks.length>0&&c.checks.length<=32
 &&c.checks.every(x=>x&&typeof x==='object'&&typeof x.passed==='boolean'&&typeof x.code==='string')
 &&Array.isArray(c.rejection)&&c.rejection.every(x=>typeof x==='string')
 &&['name','entry_reason','confirmation','cancel','score_basis'].every(k=>typeof c[k]==='string')
 &&c.indicators&&['ema20','ema50','atr','rsi','macd','histogram'].every(k=>Number.isFinite(c.indicators[k]))
 &&c.horizon&&[c.horizon.min_seconds,c.horizon.max_seconds].every(Number.isFinite)
 &&c.horizon.min_seconds>0&&c.horizon.min_seconds<=c.horizon.max_seconds&&c.horizon.max_seconds<=14400
 &&(!levels(c)||(c.stop_explanation&&c.target_explanation&&Number.isFinite(c.stop_explanation.anchor)
 &&typeof c.stop_explanation.reason==='string'&&typeof c.target_explanation.reason==='string')));}
function fresh(data,c,now){const q=data?.quotes?.[c?.frame];return !!(evidence(c)&&data?.explanation_version===VERSION&&data.scope==='AURA6_PUBLIC_OBSERVER_ONLY'
 &&data.execution_enabled===false&&data.account_connected===false&&data.observer?.running===true
 &&Number.isFinite(now)&&Number.isFinite(data.server_time)&&Math.abs(now-data.server_time)<=10
 &&data.fresh_frames?.includes(c.frame)&&c.version===VERSION&&c.source===SOURCE&&q?.source===SOURCE
 &&c.statistical_status==='UNVALIDATED'&&c.probability_tp_before_sl===null&&c.exchange_execution===false&&c.manual_only===true
 &&Object.hasOwn(FRAMES,c.frame)&&Object.hasOwn(NAMES,c.strategy)&&['LONG','SHORT'].includes(c.direction)&&['WATCH','REJECTED'].includes(c.state)
 &&typeof c.model_sha256==='string'&&/^[a-f0-9]{64}$/.test(c.model_sha256)
 &&Number.isInteger(c.score)&&c.score>=0&&c.score<=100
 &&[q.bid,q.ask,q.time,q.received_at,c.closed_at,c.valid_until].every(Number.isFinite)
 &&q.bid>0&&q.ask>=q.bid&&(q.ask-q.bid)/q.bid<=.002&&now>=q.time&&now-q.time<=5&&now>=q.received_at&&now-q.received_at<=5
 &&c.quote_time===q.time&&c.quote_received_at===q.received_at&&c.closed_at===Math.floor(now/FRAMES[c.frame])*FRAMES[c.frame]
 &&c.valid_until===c.closed_at+FRAMES[c.frame]&&now<c.valid_until);}
function levels(c){if(!c||!['LONG','SHORT'].includes(c.direction))return false;const sign=c.direction==='LONG'?1:-1;return [c.entry,c.sl,c.tp,c.net_rr,c.gross_rr,c.costs?.net_loss].every(Number.isFinite)
 &&Math.min(c.entry,c.sl,c.tp)>0&&sign*(c.entry-c.sl)>0&&sign*(c.tp-c.entry)>0&&c.costs.net_loss>0;}
function usable(data,c,now,threshold=0){const q=data?.quotes?.[c?.frame];return !!(fresh(data,c,now)&&c.state==='WATCH'&&c.score>=threshold
 &&Array.isArray(c.checks)&&c.checks.length>0&&c.checks.every(x=>x.passed===true)&&c.rejection?.length===0&&levels(c)&&c.net_rr>=1.5
 &&c.entry===q[c.direction==='LONG'?'ask':'bid']);}
function position(c,risk){return Number.isFinite(risk)&&risk>0&&levels(c)?risk/c.costs.net_loss:null;}
const HISTORY_KEY='aura5.explainable.watch-history.v1';
const watchKey=c=>[c.model_sha256,c.id,c.strategy,c.frame,c.direction,c.closed_at].join(':');
class WatchHistory{
 constructor(storage){this.storage=storage;this.rows=[];this.available=true;
  try{const raw=storage.getItem(HISTORY_KEY)||'[]';if(raw.length>2000000)throw Error('LIMIT');
   const rows=JSON.parse(raw);if(!Array.isArray(rows))throw Error('FORMAT');
   this.rows=rows.filter(r=>Number.isFinite(r?.at)&&evidence(r.c)&&levels(r.c)&&r.c.state==='WATCH'
    &&Object.hasOwn(NAMES,r.c.strategy)&&Object.hasOwn(FRAMES,r.c.frame)&&r.key===watchKey(r.c)).slice(-100);
  }catch{this.available=false;}}
 observe(data,now){let changed=false;
  for(const c of candidateRows(data)){if(!usable(data,c,now)||typeof c.id!=='string'||!/^[a-f0-9]{64}$/.test(c.id)||this.rows.some(r=>r.key===watchKey(c)))continue;
   const raw=JSON.stringify(c);if(raw.length>16000)continue;
   this.rows.push({key:watchKey(c),at:now,c:JSON.parse(raw)});changed=true;
  }
  if(changed){this.rows=this.rows.slice(-100);try{this.storage.setItem(HISTORY_KEY,JSON.stringify(this.rows));}catch{this.available=false;}}
  return changed;
 }
}
const api={VERSION,FRAMES,NAMES,candidates:candidateRows,evidence,fresh,levels,usable,position,WatchHistory,HISTORY_KEY,watchKey};root.AuraExplainable=api;if(typeof module!=='undefined')module.exports=api;
if(!root.document)return;
const host=document.getElementById('aura-explainable');if(!host)return;
const add=(tag,text,parent)=>{const e=document.createElement(tag);e.textContent=text;parent.append(e);return e;};
const fmt=n=>Number.isFinite(n)?n.toFixed(2):'—',label=k=>LABELS[k]||k;
const reasons=c=>Array.isArray(c?.rejection)?c.rejection.filter(x=>typeof x==='string'):[];
add('h2','Что увидела Aura · LONG и SHORT',host);
add('p','Три независимые стратегии на закрытых свечах Bitget. Балл 0–100 — доля выполненных условий, не вероятность прибыли. WATCH — технические условия пройдены; REJECTED — есть отказ; UNKNOWN — данные не подтверждены. NO_EDGE_FOUND · CONFIRMED недоступен.',host);
const riskLabel=add('label','Риск на сценарий, USDT ',host),risk=add('input','',riskLabel);risk.type='number';risk.min='0.01';risk.step='0.01';risk.placeholder='Введите допустимый убыток';risk.id='explain-risk';
add('p','Размер позиции — расчёт по модельному убытку на SL с расходами; комиссии и funding нужно сверять. Гэп и реальное проскальзывание могут увеличить убыток.',host);
const audio=add('button','Включить звук WATCH · открытая вкладка',host);audio.type='button';
const audioStatus=add('p','Звук выключен. Фоновые уведомления не гарантируются.',host);
const player=new root.AuraSignalAlerts.WebAudioPlayer();let audioReady=false,audioBusy=false;
async function notify(now){
 if(!audioReady||audioBusy||document.hidden||!navigator.locks?.request)return;
 const candidates=candidateRows(latest).filter(c=>usable(latest,c,now));if(!candidates.length)return;audioBusy=true;
 try{await navigator.locks.request('aura5.explainable.audio',()=>{
  const key='aura5.explainable.audio.v1',seen=JSON.parse(localStorage.getItem(key)||'[]');
  if(!Array.isArray(seen)||seen.length>500||seen.some(x=>typeof x!=='string'||!/^[a-f0-9]{64}$/.test(x)))throw Error('INVALID_DEDUP');
  const c=candidates.find(c=>/^[a-f0-9]{64}$/.test(c.id)&&!seen.includes(c.id)&&usable(latest,c,Date.now()/1000));if(!c)return;
  localStorage.setItem(key,JSON.stringify([...seen,c.id].slice(-500)));
  audioStatus.textContent=player.play(c.direction,.3)!==false?'Web Audio запланирован для '+c.direction+' · '+c.name+'; слышимость не подтверждена':'Звук недоступен';
 });}catch{audioReady=false;player.suspend();audioStatus.textContent='Звук отключён: локальное исключение дублей недоступно';}finally{audioBusy=false;}
}
audio.onclick=async()=>{if(audioReady){audioReady=false;player.suspend();audio.textContent='Включить звук WATCH · открытая вкладка';audioStatus.textContent='Звук выключен';return;}
 if(!navigator.locks?.request){audioStatus.textContent='Без безопасного исключения дублей звук недоступен';return;}
 try{audioReady=await player.activate();}catch{audioReady=false;}audio.textContent=audioReady?'Выключить звук WATCH':'Включить звук WATCH · открытая вкладка';if(audioReady)void notify(Date.now()/1000);};
let latest=null,initialized=false,selected=null;
const slots=[];
const storage=(()=>{try{return localStorage;}catch{return {getItem(){throw Error('UNAVAILABLE');},setItem(){throw Error('UNAVAILABLE');}};}})();
const archive=new WatchHistory(storage),history=add('details','',host);
history.className='explain-history';add('summary','История проверенных WATCH · снимки, не действующие сигналы',history);
const historyStatus=add('p','',history),historyList=add('ol','',history),historyNodes=new Map();
function historyPaint(){
 text(historyStatus,archive.available?'Локальная история этого браузера · до 100 WATCH. Сохранённые уровни не обновляются и не разрешают вход.':'Хранилище недоступно: история сохраняется только до закрытия вкладки.');
 for(const row of archive.rows.slice().reverse()){
  if(historyNodes.has(row.key))continue;
  const c=row.c,li=add('li','',historyList);li.dataset.watchKey=row.key;
  add('strong','НЕАКТУАЛЕН · сохранённый WATCH · '+c.direction+' · '+c.frame+' · '+c.name,li);
  add('p',new Date(row.at*1000).toISOString()+' · Entry '+fmt(c.entry)+' · SL '+fmt(c.sl)+' · TP '+fmt(c.tp)+' · Net R/R '+fmt(c.net_rr),li);
  add('p','Причина входа: '+c.entry_reason+' · Подтверждение: '+c.confirmation+' · Отмена: '+c.cancel,li);
  historyNodes.set(row.key,li);
 }
 for(const [key,node] of historyNodes)if(!archive.rows.some(r=>r.key===key)){node.remove();historyNodes.delete(key);}
}
function text(node,value){if(node.textContent!==value)node.textContent=value;}
function hide(node,hidden){if(node.hidden!==hidden)node.hidden=hidden;}
function zoneList(candidate){
 return Array.isArray(candidate?.zones)?candidate.zones.filter(z=>z&&['SUPPORT','RESISTANCE'].includes(z.kind)
  &&Number.isFinite(z.lower)&&Number.isFinite(z.upper)&&z.lower>0&&z.upper>z.lower
  &&Number.isInteger(z.touches)&&z.touches>=2&&Number.isFinite(z.confirmed_at)&&z.confirmed_at<candidate.closed_at).slice(0,2):[];
}
const cards=add('div','',host);cards.className='sc-cards explain-cards';
for(const frame of Object.keys(FRAMES))for(const direction of ['LONG','SHORT']){
 const card=add('article','',cards);card.dataset.frame=frame;card.dataset.direction=direction;
 const title=add('h3','',card),description=add('p','',card),refusal=add('p','',card),plan=add('section','',card);
 const planStatus=add('strong','',plan),metrics=add('dl','',plan);metrics.className='explain-plan';
 const values={};
 for(const [key,label] of [['entry','Entry'],['sl','Stop Loss'],['tp','Take Profit'],['net_rr','Net R/R']]){
  const item=add('div','',metrics);add('dt',label,item);values[key]=add('dd','',item);
 }
 const size=add('p','',plan),button=add('button','На графике',card);button.type='button';
 const detail=add('details','',card);add('summary','Почему такой сигнал',detail);
 const body=add('div','',detail);
 const pin=add('button','Закрепить сигнал',card);pin.type='button';pin.setAttribute('aria-pressed','false');
 const slot={frame,direction,card,title,description,refusal,plan,planStatus,values,size,button,detail,body,pin};
 pin.onclick=()=>{slot.snapshot=slot.snapshot?null:slot.reading?JSON.parse(JSON.stringify(slot.reading)):null;
  pin.setAttribute('aria-pressed',String(!!slot.snapshot));pin.textContent=slot.snapshot?'Открепить снимок':'Закрепить сигнал';render();};
 slots.push(slot);
 button.addEventListener('click',()=>{
  selected={frame,direction,id:slot.id};
  document.getElementById('app-tab-chart')?.click();
  document.querySelector('#timeframes [data-tf="'+frame+'"]')?.click();
  render();
 });
}
function render(){
 const now=Date.now()/1000;
 archive.observe(latest,now);historyPaint();
 void notify(now);
 const all=candidateRows(latest),overlays={};
 for(const slot of slots){
  const {frame,direction,card,title,description,refusal,plan,planStatus,values,size,button,detail,body}=slot;
  const rows=all.filter(c=>c.frame===frame&&c.direction===direction&&Object.hasOwn(NAMES,c.strategy));
  const verified=rows.filter(c=>fresh(latest,c,now));
  verified.sort((a,b)=>Number(usable(latest,b,now))-Number(usable(latest,a,now))
   ||Number(b.id===slot.id)-Number(a.id===slot.id)||b.score-a.score);
  const x=slot.snapshot||verified[0],watch=!slot.snapshot&&usable(latest,x,now),state=slot.snapshot?'SNAPSHOT':x?(watch?'WATCH':'REJECTED'):'UNKNOWN';
  if(card.dataset.state!==state)card.dataset.state=state;
  if(x&&x.id!==slot.id){slot.id=x.id;card.dataset.scenarioId=x.id;}
  if(watch)slot.lastPlan=x;
  if(!slot.lastPlan){const old=archive.rows.slice().reverse().find(r=>r.c.frame===frame&&r.c.direction===direction);if(old)slot.lastPlan=old.c;}
  const historical=!watch&&!slot.snapshot&&slot.lastPlan;
  const displayed=slot.snapshot&&levels(slot.snapshot)?slot.snapshot:watch?x:historical||(x&&levels(x)?x:null);
  slot.reading=displayed||x||historical||null;slot.pin.disabled=!slot.reading;
  hide(plan,!displayed);
  text(title,direction+' · '+frame+' · '+({WATCH:'ЕСТЬ ТЕХНИЧЕСКИЙ СЦЕНАРИЙ',REJECTED:'НЕ ВХОДИТЬ',UNKNOWN:'НЕДОСТАТОЧНО ДАННЫХ',SNAPSHOT:'СНИМОК · НЕ ДЕЙСТВУЮЩИЙ СИГНАЛ'}[state])+(x?' · '+x.score+'/100':''));
  const missing=reasons(rows.find(c=>c.state==='UNKNOWN')).map(label).join(' · ');
  text(description,(x?'Стратегия: '+x.name:'Данные не подтверждены. '+(missing||'Нет свежего снимка котировок и закрытых свечей.'))+(!displayed?' Entry/SL/TP не рассчитаны: нет проверенного корректного плана.':''));
  hide(refusal,state!=='REJECTED');
  text(refusal,state==='REJECTED'?'Отказ: '+(reasons(x).map(label).join(' · ')||'План не прошёл проверку'): '');
  if(displayed){
   text(planStatus,slot.snapshot?'ЗАКРЕПЛЁННЫЙ СНИМОК · НЕАКТУАЛЕН · '+new Date(displayed.quote_time*1000).toISOString()+' · рынок продолжает обновляться':historical?'НЕАКТУАЛЕН · '+displayed.name+' · '+new Date(displayed.quote_time*1000).toISOString()
    :watch?'План WATCH':'Отклонённый расчёт');
   for(const key of Object.keys(values))text(values[key],fmt(displayed[key]));
  }
  const quantity=watch?position(x,Number(risk.value)):null;
  text(size,quantity===null?'':'Размер позиции ≤ '+quantity.toFixed(6)+' BTC · номинал '+fmt(quantity*x.entry)+' USDT.');
  hide(size,quantity===null);
  const zones=slot.snapshot?[]:zoneList(x);
  if(zones.length)overlays[frame]={zones};
  const canShow=!slot.snapshot&&!!x&&(watch||zones.length>0);
  hide(button,!canShow);
  hide(detail,!x&&!historical);
  if(x){
   const alternatives=verified.slice(1).map(c=>c.name+' · '+c.state+' · '+c.score+'/100 · '+reasons(c).map(label).join(' · '));
   const signature=JSON.stringify([x.id,state,x.checks,x.rejection,x.indicators,x.stop_explanation?.anchor,x.target_explanation?.reason,levels(x),zones,alternatives]);
   if(signature!==slot.detailSignature){
    slot.detailSignature=signature;
    body.replaceChildren();
    const met=x.checks.filter(c=>c.passed).map(c=>label(c.code));
    add('p','Aura увидела: '+(met.join(' · ')||'условия пока не выполнены'),body);
    for(const c of x.checks)add('p',(c.passed?'Выполнено: ':'Не выполнено: ')+label(c.code)+' · факт '+JSON.stringify(c.actual)+' · нужно '+JSON.stringify(c.required),body);
    add('p','Индикаторы: '+Object.entries(x.indicators).map(([k,v])=>k+' '+fmt(v)).join(' · '),body);
    if(x.stop_explanation){
     const stop=x.stop_explanation;
     add('p','Почему SL здесь: ATR14 '+fmt(stop.atr)+' USDT. '+stop.reason+' · уровень отмены '+fmt(stop.anchor),body);
    }
    if(x.target_explanation)add('p','Почему TP здесь: '+x.target_explanation.reason,body);
    for(const zone of zones)add('p',(zone.kind==='SUPPORT'?'Поддержка ':'Сопротивление ')+fmt(zone.lower)+'–'+fmt(zone.upper)+' · касаний '+zone.touches,body);
    if(levels(x))add('p','Почему вход здесь: '+x.entry_reason,body);
    if(levels(x))add('p','Расходы в Net R/R: комиссия, проскальзывание и funding-резерв. Вход по Ask/Bid, спред повторно не вычитается.',body);
    add('p','Для входа: '+x.confirmation,body);
    add('p','Отмена: '+x.cancel.replaceAll('anchor','уровня отмены'),body);
    add('p','Ориентир удержания '+Math.round(x.horizon.min_seconds/60)+'–'+Math.round(x.horizon.max_seconds/60)+' мин. Если SL/TP не достигнуты, пересмотреть выход к концу этого окна.',body);
    add('p','Закрытие свечи '+new Date(x.closed_at*1000).toISOString()+' · срок входа до '+new Date(x.valid_until*1000).toISOString(),body);
    for(const alternative of alternatives)add('p','Другой сценарий: '+alternative,body);
   }
  }else if(slot.detailSignature!==null){
   slot.detailSignature=null;body.replaceChildren();
   if(historical)add('p','Последний подтверждённый план сохранён для истории в этой вкладке.',body);
  }
 }
 if(selected){
  const chosen=all.find(c=>c.frame===selected.frame&&c.direction===selected.direction&&c.id===selected.id&&usable(latest,c,now));
  if(chosen)overlays[chosen.frame]={zones:zoneList(chosen),plan:chosen};
 }
 root.dispatchEvent(new CustomEvent('aura-explainable-chart',{detail:overlays}));
}
risk.addEventListener('input',render);
root.addEventListener('aura-preview-snapshot',event=>{latest=event.detail;
 if(!initialized&&latest?.explanation_version===VERSION){initialized=true;const legacy=document.getElementById('aura-score-diagnostics');if(legacy)legacy.open=false;}
 render();});
document.addEventListener('visibilitychange',()=>{latest=null;audioReady=false;player.suspend();audio.textContent='Включить звук WATCH · открытая вкладка';render();});
setInterval(render,1000);render();
})(typeof window==='undefined'?globalThis:window);


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
function levels(c){if(!c||typeof c!=='object')return false;const sign=c.direction==='LONG'?1:-1;return [c.entry,c.sl,c.tp,c.net_rr,c.gross_rr,c.costs?.net_loss].every(Number.isFinite)
 &&Math.min(c.entry,c.sl,c.tp)>0&&sign*(c.entry-c.sl)>0&&sign*(c.tp-c.entry)>0&&c.costs.net_loss>0;}
function usable(data,c,now,threshold=0){const q=data?.quotes?.[c?.frame];return !!(fresh(data,c,now)&&c.state==='WATCH'&&c.score>=threshold
 &&Array.isArray(c.checks)&&c.checks.length>0&&c.checks.every(x=>x.passed===true)&&c.rejection?.length===0&&levels(c)&&c.net_rr>=1.5
 &&c.entry===q[c.direction==='LONG'?'ask':'bid']);}
function position(c,risk){return Number.isFinite(risk)&&risk>0&&levels(c)?risk/c.costs.net_loss:null;}
const api={VERSION,FRAMES,NAMES,candidates:candidateRows,evidence,fresh,levels,usable,position};root.AuraExplainable=api;if(typeof module!=='undefined')module.exports=api;
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
const cards=add('div','',host);cards.className='sc-cards explain-cards';
let latest=null,initialized=false,lastSignature=null;
function render(){const clock=Date.now()/1000;void notify(clock);const signature=JSON.stringify([latest,candidateRows(latest).map(c=>fresh(latest,c,clock)),risk.value]);if(signature===lastSignature)return;lastSignature=signature;const opened=new Set([...cards.querySelectorAll('article')].filter(c=>c.querySelector('details')?.open).map(c=>c.dataset.frame+':'+c.dataset.direction));cards.replaceChildren();const now=Date.now()/1000;
 for(const frame of Object.keys(FRAMES))for(const direction of ['LONG','SHORT']){
  const rows=candidateRows(latest).filter(c=>c.frame===frame&&c.direction===direction&&NAMES[c.strategy]);
  rows.sort((a,b)=>Number(usable(latest,b,now))-Number(usable(latest,a,now))||(b.score??-1)-(a.score??-1));
  const x=rows[0],known=x&&fresh(latest,x,now),state=known?(usable(latest,x,now)?'WATCH':'REJECTED'):'UNKNOWN';
  const card=add('article','',cards);card.dataset.frame=frame;card.dataset.direction=direction;card.dataset.state=state;
  add('h3',direction+' · '+frame+' · '+state+(known?' · '+x.score+'/100':''),card);
  if(!known){add('p','Данные не подтверждены. Балл и уровни недоступны. '+reasons(x).map(label).join('; '),card);continue;}
  add('p','Стратегия: '+x.name,card);
  const met=x.checks.filter(c=>c.passed).map(c=>label(c.code)),miss=x.checks.filter(c=>!c.passed).map(c=>label(c.code));
  add('p','Aura увидела: '+(met.join('; ')||'условия пока не выполнены')+'.',card);
  if(state==='REJECTED')add('p','Отказ: '+([...reasons(x).map(label),...miss].filter((v,i,a)=>a.indexOf(v)===i).join('; ')||'Сценарий не прошёл проверку'),card);
  if(levels(x)){
   add('p','Entry '+fmt(x.entry)+' · SL '+fmt(x.sl)+' · TP '+fmt(x.tp)+' USDT',card);
   add('p','Почему вход здесь: '+x.entry_reason,card);
   add('p','Почему SL здесь: '+x.stop_explanation.reason+' Уровень отмены '+fmt(x.stop_explanation.anchor)+' USDT.',card);
   add('p','Почему TP здесь: '+x.target_explanation.reason+' '+fmt(x.tp)+' USDT.',card);
   add('p','Gross R/R '+fmt(x.gross_rr)+' · Net R/R '+fmt(x.net_rr),card);
   const quantity=position(x,Number(risk.value));
   add('p',quantity===null?'Для расчёта размера позиции задайте риск в USDT.':'Размер позиции ≤ '+quantity.toFixed(6)+' BTC · номинал '+fmt(quantity*x.entry)+' USDT. Расчётный риск '+fmt(Number(risk.value))+' USDT.',card);
  }
  add('p','Для входа: '+x.confirmation,card);
  add('p','Отмена: '+x.cancel.replaceAll('anchor','уровня отмены'),card);
  add('p','Ориентир удержания '+Math.round(x.horizon.min_seconds/60)+'–'+Math.round(x.horizon.max_seconds/60)+' мин. Если SL/TP не достигнуты, пересмотреть выход не позже чем через '+Math.round(x.horizon.max_seconds/60)+' мин после входа. Это оценка, не гарантия.',card);
  const detail=add('details','',card);detail.open=opened.has(frame+':'+direction);add('summary','Почему такой сигнал',detail);
  for(const c of x.checks)add('p',(c.passed?'Выполнено: ':'Не выполнено: ')+label(c.code)+' · факт '+JSON.stringify(c.actual)+' · нужно '+JSON.stringify(c.required),detail);
  add('p','Индикаторы: '+Object.entries(x.indicators).map(([k,v])=>k+' '+fmt(v)).join(' · '),detail);
  if(x.stop_explanation){const s=x.stop_explanation;add('p','ATR'+s.atr_period+' '+fmt(s.atr)+' USDT ('+s.atr_method+'). Anchor '+fmt(s.anchor)+'. '+s.formula+'. Расстояние '+fmt(s.distance_usdt)+' USDT / '+fmt(s.distance_percent)+'%.',detail);}
  if(x.costs)add('p','На 1 BTC: комиссия при SL '+fmt(x.costs.stop_fees)+', при TP '+fmt(x.costs.target_fees)+' USDT; funding-резерв '+fmt(x.costs.funding_reserve)+' USDT. Комиссия .1%/сторона, проскальзывание .05%/сторона; Entry уже Ask/Bid, SL/TP — котировки выхода, спред повторно не вычитается. Это модель расходов, не фактический тариф или funding.',detail);
  add('p','Закрытие свечи '+new Date(x.closed_at*1000).toISOString()+'; вход действует до '+new Date(x.valid_until*1000).toISOString()+'. '+x.score_basis,detail);
  for(const other of rows.slice(1))add('p','Другой сценарий: '+other.name+' · '+(fresh(latest,other,now)?other.state+' · '+other.score+'/100':'UNKNOWN')+' · '+reasons(other).map(label).join('; '),detail);
 }
}
risk.addEventListener('input',render);
root.addEventListener('aura-preview-snapshot',event=>{latest=event.detail;
 if(!initialized&&latest?.explanation_version===VERSION){initialized=true;const legacy=document.getElementById('aura-score-diagnostics');if(legacy)legacy.open=false;}
 render();});
document.addEventListener('visibilitychange',()=>{latest=null;audioReady=false;player.suspend();audio.textContent='Включить звук WATCH · открытая вкладка';render();});
setInterval(render,1000);render();
})(typeof window==='undefined'?globalThis:window);

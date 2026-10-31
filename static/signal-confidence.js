/* Aura 5.0 research-only scoring. Never sends orders or modifies exchange accounts. */
(function(root){'use strict';
const SOURCE='BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2';
const VERSION='AURA5_TECHNICAL_SCORE_V1_FROZEN';
const STORE='aura5.signal-confidence.v1';
const AUDIO_STORE='aura5.signal-confidence.audio-dedup.v1';
const STEPS={'5m':300,'15m':900,'1h':3600,'4h':14400};
const GROUPS={trend:'Тренд EMA20/50/200',momentum:'Импульс RSI/MACD',structure:'Структура рынка',volume:'Объём',support_resistance:'Уровни S/R'};
const CAPS={trend:30,momentum:25,structure:20,volume:10,support_resistance:15};

function manualCosts(candidate,levels){
 // Same frozen AURA5_EXIT_QUOTE_COSTS_2 convention as app/hunter/costs.py:
 // displayed Entry is an executable quote; SL/TP are exit-side quotes.
 if(!candidate||candidate.costs?.cost_version!=='AURA5_EXIT_QUOTE_COSTS_2'
   ||candidate.costs?.entry_basis!=='EXECUTABLE_QUOTE'||!STEPS[candidate.frame]
   ||!Array.isArray(levels)||levels.length!==3||levels.some(x=>!Number.isFinite(x)||x<=0))return null;
 const sign=candidate.direction==='LONG'?1:candidate.direction==='SHORT'?-1:0;
 if(!sign)return null;
 const [entry,sl,tp]=levels,filledEntry=entry*(1+sign*.0005);
 if(sign*(filledEntry-sl)<=0||sign*(tp-filledEntry)<=0)return null;
 const filledStop=sl*(1-sign*.0005),filledTarget=tp*(1-sign*.0005);
 const funding=entry*Math.ceil(24*STEPS[candidate.frame]/28800)*.0001;
 const stopFees=.001*(filledEntry+filledStop),targetFees=.001*(filledEntry+filledTarget);
 const netLoss=sign*(filledEntry-filledStop)+stopFees+funding;
 const netReward=sign*(filledTarget-filledEntry)-targetFees-funding;
 if(!(netLoss>0)||!Number.isFinite(netReward))return null;
 return {net_rr:netReward/netLoss,net_loss:netLoss,net_reward:netReward,
         stop_fees:stopFees,target_fees:targetFees,funding_reserve:funding,
         cost_version:'AURA5_EXIT_QUOTE_COSTS_2'};
}

function validThreshold(x){return Number.isSafeInteger(x)&&x>=50&&x<=100;}
function reserveAudio(storage,id){
 if(typeof id!=='string'||!/^[a-f0-9]{64}$/.test(id))return false;
 const raw=storage.getItem(AUDIO_STORE);
 if(raw&&raw.length>50000)throw Error('AUDIO_DEDUP_LIMIT');
 const parsed=JSON.parse(raw||'[]');
 if(!Array.isArray(parsed)||parsed.length>500||parsed.some(x=>typeof x!=='string'||!/^[a-f0-9]{64}$/.test(x)))throw Error('INVALID_AUDIO_DEDUP');
 if(parsed.includes(id))return false;
 storage.setItem(AUDIO_STORE,JSON.stringify([...parsed,id].slice(-500)));
 return true;
}
function usable(data,c,now,threshold=50){
 const q=data?.quotes?.[c?.frame],sign=c?.direction==='LONG'?1:c?.direction==='SHORT'?-1:0;
 return !!(validThreshold(threshold)&&data?.scope==='AURA6_PUBLIC_OBSERVER_ONLY'&&data.execution_enabled===false
  &&data.account_connected===false&&data.observer?.running===true&&data.confidence_version===VERSION
  &&Array.isArray(data.confidence_candidates)&&c?.score_version===VERSION&&c?.source===SOURCE
  &&c?.statistical_status==='UNVALIDATED'&&c.probability_tp_before_sl===null
  &&c.state==='WATCH_RESEARCH'
  &&c.model_sha256===data.model_sha256
  &&typeof c.score_model_sha256==='string'&&/^[a-f0-9]{64}$/.test(c.score_model_sha256)
  &&c.exchange_execution===false&&c.manual_only===true&&sign!==0&&STEPS[c.frame]
  &&Number.isSafeInteger(c.score)&&c.score>=threshold&&c.score<=100
  &&data.fresh_frames?.includes(c.frame)&&q?.source===SOURCE
  &&[now,data.server_time,q.time,q.received_at,q.bid,q.ask,c.quote_time,c.quote_received_at,c.closed_at,c.valid_until,
     c.entry,c.sl,c.tp,c.net_rr].every(Number.isFinite)
  &&Math.abs(now-data.server_time)<=10&&now>=q.time&&now-q.time<=5
  &&now>=q.received_at&&now-q.received_at<=5&&q.bid>0&&q.ask>=q.bid&&(q.ask-q.bid)/q.bid<=.002
  &&c.quote_time===q.time&&c.quote_received_at===q.received_at&&c.bid===q.bid&&c.ask===q.ask
  &&c.closed_at%STEPS[c.frame]===0
  &&c.closed_at<=now&&now<c.valid_until&&c.valid_until===c.closed_at+STEPS[c.frame]
  &&c.risk_gates_passed===true&&c.net_rr>=1.5
  &&Math.abs(c.entry-(sign===1?q.ask:q.bid))<1e-7
  &&c.entry>0&&c.sl>0&&c.tp>0&&sign*(c.entry-c.sl)>0&&sign*(c.tp-c.entry)>0
  &&c.score_groups&&Object.keys(c.score_groups).length===5&&Object.keys(CAPS).every(k=>
    Number.isSafeInteger(c.score_groups[k])&&c.score_groups[k]>=0&&c.score_groups[k]<=CAPS[k])
  &&Object.values(c.score_groups).reduce((a,b)=>a+b,0)===c.score);
}

class LocalJournal{
 constructor(storage){this.storage=storage;this.threshold=50;this.rows=[];this.available=true;
  try{const raw=storage.getItem(STORE);if(raw&&raw.length>150000)throw Error('LIMIT');const x=JSON.parse(raw||'null');
   if(x){if(validThreshold(x.threshold))this.threshold=x.threshold;
    if(Array.isArray(x.rows))this.rows=x.rows.filter(r=>r&&typeof r.id==='string'&&/^[a-f0-9]{64}$/.test(r.id)
     &&['LONG','SHORT'].includes(r.direction)&&Number.isSafeInteger(r.score)&&r.score>=0&&r.score<=100
     &&Number.isFinite(r.seen_at)&&Number.isFinite(r.closed_at)&&Number.isFinite(r.quote_time))
     .slice(-200).map(r=>({...r,manual_adjustments:Array.isArray(r.manual_adjustments)?r.manual_adjustments.slice(-30):[],
      alerted_at:Number.isFinite(r.alerted_at)?r.alerted_at:null,
      copied_at:Number.isFinite(r.copied_at)?r.copied_at:null}));}
  }catch{this.available=false;}}
 save(){try{this.storage.setItem(STORE,JSON.stringify({threshold:this.threshold,rows:this.rows.slice(-200)}));return true;}
  catch{this.available=false;return false;}}
 seen(c,now){if(!usableId(c)||!Number.isFinite(now))return false;
  if(this.rows.some(r=>r.id===c.id))return false;
  this.rows.push({id:c.id,score:c.score,score_version:c.score_version,model_sha256:c.model_sha256,
   score_model_sha256:c.score_model_sha256,
   input_sha256:c.input_sha256,frame:c.frame,direction:c.direction,closed_at:c.closed_at,
   quote_time:c.quote_time,seen_at:now,entry:c.entry,sl:c.sl,tp:c.tp,net_rr:c.net_rr,
   probability_tp_before_sl:null,outcome:'UNKNOWN',gap:'NO_CONTINUOUS_EXECUTION_TRACKING',
   copied_at:null,alerted_at:null,manual_adjustments:[]});this.rows=this.rows.slice(-200);this.save();return true;}
 copied(c,now){const row=this.rows.find(r=>r.id===c.id);if(!row)return false;
  // A candle id stays stable as Bid/Ask changes. Record the exact manually
  // transferred quote, never attribute the first quote's outcome to it.
  row.quote_time=c.quote_time;row.entry=c.entry;row.sl=c.sl;row.tp=c.tp;row.net_rr=c.net_rr;
  row.outcome='UNKNOWN';row.gap='MANUAL_PLAN_NOT_EXECUTED';row.modeled_r=null;
  row.copied_at=now;this.save();return true;}
 edited(id,levels,now){const row=this.rows.find(r=>r.id===id);if(!row||!levels.every(Number.isFinite)||!Number.isFinite(now))return false;
  row.manual_adjustments.push({at:now,entry:levels[0],sl:levels[1],tp:levels[2]});row.manual_adjustments=row.manual_adjustments.slice(-30);
  this.save();return true;}
 outcomes(history){if(!Array.isArray(history))return false;let changed=false;
  for(const event of history.slice(0,100)){const row=this.rows.find(r=>r.id===event?.id);
   if(!row||event.score_version!==VERSION||event.score_model_sha256!==row.score_model_sha256
     ||event.score!==row.score||event.input_sha256!==row.input_sha256
     ||event.quote_time!==row.quote_time
     ||!['PENDING','OPEN','UNKNOWN','NO_FILL','TP','SL','TIMEOUT'].includes(event.outcome))continue;
   if(row.outcome!==event.outcome||row.gap!==(event.result?.note||'PENDING_FORWARD')){
    row.outcome=event.outcome;row.gap=event.result?.note||'PENDING_FORWARD';
    row.modeled_r=Number.isFinite(event.result?.r)?event.result.r:null;changed=true;}
  }
  if(changed)this.save();return changed;}
}
function usableId(c){return typeof c?.id==='string'&&/^[a-f0-9]{64}$/.test(c.id);}
root.Aura5Confidence={usable,validThreshold,reserveAudio,manualCosts,LocalJournal,VERSION,STORE};
if(typeof module!=='undefined')module.exports={usable,validThreshold,reserveAudio,manualCosts,LocalJournal,VERSION,STORE};
if(!root.document||document.body.dataset.manualPreview!=='true')return;
const host=document.getElementById('aura-confidence');if(!host)return;
const add=(tag,value,parent)=>{const e=document.createElement(tag);e.textContent=value;parent.append(e);return e;};
const storage=(()=>{try{return localStorage;}catch{return {getItem(){throw Error('UNAVAILABLE');},setItem(){throw Error('UNAVAILABLE');}};}})();
const journal=new LocalJournal(storage);
add('h2','Signal Confidence · исследовательские LONG/SHORT',host);
add('p','Балл 0–100 показывает согласованность технических факторов, НЕ вероятность прибыли. Даже 80/100 не означает 80% выигрышных сделок. Вероятность TP раньше SL: UNKNOWN · недостаточно независимых данных. CONFIRMED запрещён (NO_EDGE_FOUND).',host);
const controls=add('div','',host);controls.className='sc-controls';
const label=add('label','Минимальный балл ',controls),range=add('input','',label);range.type='range';range.min='50';range.max='100';range.step='1';range.value=String(journal.threshold);
const value=add('strong',String(journal.threshold)+'/100',label);
const status=add('p','Ожидание свежих данных Bitget…',host);status.setAttribute('role','status');
const audioButton=add('button','Включить WATCH-звук ≥ порога · только эта вкладка',controls);audioButton.type='button';
const audioStatus=add('span','Звук выключен; фоновые уведомления не гарантируются',controls);
const player=new root.AuraSignalAlerts.WebAudioPlayer();
let audioReady=false,notifying=false;
const cards=add('div','',host);cards.className='sc-cards';
const manual=add('section','',host);manual.className='sc-manual';
add('h3','Ручной план для Bybit Demo · без подключения к аккаунту',manual);
const manualDescription=add('p','Выберите свежую исследовательскую гипотезу. Перенос заполняет только эти локальные поля, без PAPER и без ордеров.',manual);
const manualFields={};
for(const [key,title] of [['direction','Направление'],['entry','Entry · USDT'],['sl','Stop Loss · USDT'],['tp','Take Profit · USDT']]){
 const label=add('label',title,manual),field=add('input','',label);
 field.type='text';field.id='sc-manual-'+key;field.autocomplete='off';
 field.readOnly=key==='direction';field.placeholder='Нет выбранного плана';
 manualFields[key]=field;
}
const clipboard=add('button','Скопировать уровни для ручной сверки в Bybit Demo',manual);clipboard.type='button';
const manualStatus=add('p','Нет выбранного плана',manual);manualStatus.setAttribute('role','status');
const history=add('details','',host);add('summary','Локальный журнал · просмотр и экспорт',history);
const exportButton=add('button','Скачать JSON журнала',history);exportButton.type='button';
const historyList=add('ol','',history);
let latest=null,copiedId=null,copiedSource=null,requestId=0;
function historyPaint(){historyList.replaceChildren();for(const r of journal.rows.slice(-20).reverse())add('li',
  new Date(r.seen_at*1000).toISOString()+' · '+r.direction+' '+r.frame+' · '+r.score+'/100 · '+r.outcome+
  ' ('+r.gap+')'+(r.copied_at?' · перенесён вручную':'')+(r.manual_adjustments.length?' · правок: '+r.manual_adjustments.length:''),historyList);}
function freshRows(d,now){return (d.confidence_candidates||[]).filter(c=>usable(d,c,now,journal.threshold))
 .sort((a,b)=>b.score-a.score||a.frame.localeCompare(b.frame)||a.direction.localeCompare(b.direction));}
function textLevels(c){return 'Entry '+c.entry.toFixed(2)+' · SL '+c.sl.toFixed(2)+' · TP '+c.tp.toFixed(2)+' · Net R/R '+c.net_rr.toFixed(2);}
function editedLevels(){return ['entry','sl','tp'].map(k=>Number(manualFields[k].value));}
function manualRecalculate(){const calculated=manualCosts(copiedSource,editedLevels());
 if(!calculated||calculated.net_rr<1.5){manualStatus.textContent='Ручной план не проходит геометрию или net R/R ≥ 1.5 с расходами. Копирование заблокировано.';return null;}
 manualStatus.textContent='Ручная модель: net R/R '+calculated.net_rr.toFixed(2)+
  ' · комиссия SL '+calculated.stop_fees.toFixed(2)+' / TP '+calculated.target_fees.toFixed(2)+
  ' USDT · funding-резерв '+calculated.funding_reserve.toFixed(2)+
  ' USDT / 1 BTC. Цена Entry после правки НЕ подтверждена биржей; сверяйте на Bybit Demo.';
 return calculated;}
async function maybeSound(rows){
 if(!audioReady||document.hidden||notifying||!rows.length||!navigator.locks?.request||!journal.available)return;
 notifying=true;
 try{await navigator.locks.request(STORE+'.audio',()=>{
   const current=new LocalJournal(storage);
   if(!current.available)return;
   let candidate=null;
   for(const c of rows){if(latest&&usable(latest,c,Date.now()/1000,journal.threshold)
     &&current.rows.some(r=>r.id===c.id)&&reserveAudio(storage,c.id)){
    candidate=c;break;}}
   if(!candidate)return; // independent cross-tab watermark
   const record=current.rows.find(r=>r.id===candidate.id);
   record.alerted_at=Date.now()/1000; // reserve cross-tab before playback, at most once
   if(!current.save())return;
   journal.rows=current.rows;
   try{const scheduled=player.play(candidate.direction,.3)!==false;
    audioStatus.textContent=scheduled?'Web Audio запланирован · не доказательство слышимости':'Воспроизведение недоступно';
   }catch{audioStatus.textContent='Звук не воспроизведён';}
  });}catch{audioReady=false;audioStatus.textContent='Невозможно исключить дубли; звук отключён';}
 finally{notifying=false;}
}
audioButton.onclick=async()=>{
 if(audioReady){audioReady=false;player.suspend();audioButton.textContent='Включить WATCH-звук ≥ порога · только эта вкладка';audioStatus.textContent='Звук выключен';return;}
 if(!navigator.locks?.request||!journal.available){audioStatus.textContent='Нет безопасного локального журнала/блокировок: звук недоступен';return;}
 try{audioReady=await player.activate();}catch{audioReady=false;}
 audioButton.textContent=audioReady?'Выключить WATCH-звук':'Включить WATCH-звук ≥ порога · только эта вкладка';
 audioStatus.textContent=audioReady?'Звук активен в открытой вкладке; без фоновой гарантии':'Звук недоступен';
 if(audioReady&&latest)void maybeSound(freshRows(latest,Date.now()/1000));
};
function paint(){cards.replaceChildren();if(!latest)return;const now=Date.now()/1000,rows=freshRows(latest,now);
 status.textContent=(rows.length?'WATCH · исследовательских направлений: '+rows.length:'WAIT · направлений выше порога с актуальными данными и R/R нет')+
  ' · порог '+journal.threshold+'/100 · LIVE относится только к свежей котировке Bitget, не к прибыли';
 for(const c of rows){journal.seen(c,now);const card=add('article','',cards);
  add('h3',c.direction+' · '+c.frame+' · '+c.score+'/100 · '+(c.score<65?'слабый':c.score<80?'умеренный':'сильный'),card);
  add('p','WATCH / НЕПРОВЕРЕННАЯ ГИПОТЕЗА · технический триггер '+(c.technical_trigger?'есть':'не подтверждён'),card);
  add('p',textLevels(c),card);
  add('p','Закрытая свеча '+new Date(c.closed_at*1000).toISOString()+' · Bid '+c.bid+' / Ask '+c.ask+' · источник: публичный Bitget',card);
  add('p',Object.entries(c.score_groups).map(([k,v])=>(GROUPS[k]||k)+' '+v).join(' · '),card);
  add('p','За: '+(c.factors||[]).join('; ')+' | Против: '+(c.contradictions||[]).join('; '),card);
  add('p','Расходы и Funding учтены модельно. ATR-стоп и цель 2.5R — исследовательские допущения, не прогноз. Отмена: '+c.cancel,card);
  const b=add('button','Перенести '+c.direction+' · без ордера',card);b.type='button';b.onclick=()=>copy(c.id);
 }
 journal.outcomes(latest.confidence_history);historyPaint();void maybeSound(rows);}
async function fetchFresh(){const c=new AbortController(),t=setTimeout(()=>c.abort(),8000);try{
 const r=await fetch('/api/preview/signals/snapshot',{method:'GET',credentials:'same-origin',cache:'no-store',redirect:'error',signal:c.signal});
 if(!r.ok)throw Error('UNAVAILABLE');const d=await r.json();if(d.scope!=='AURA6_PUBLIC_OBSERVER_ONLY'||d.execution_enabled!==false||d.account_connected!==false||!Number.isFinite(d.server_time)||Math.abs(Date.now()/1000-d.server_time)>10)throw Error('INVALID_SNAPSHOT');
 return d;}finally{clearTimeout(t);}}
async function copy(id){const seq=++requestId;try{const d=await fetchFresh(),now=Date.now()/1000;
 if(seq!==requestId||document.hidden)return;const c=d.confidence_candidates?.find(x=>x.id===id);if(!usable(d,c,now,journal.threshold))return;
 manualFields.direction.value=c.direction;
 for(const key of ['entry','sl','tp'])manualFields[key].value=c[key].toFixed(1);
 copiedId=c.id;copiedSource=c;journal.seen(c,now);journal.copied(c,now);
 manualDescription.textContent='Исследовательский '+c.direction+' ('+c.score+'/100), а не подтверждённый сигнал.';
 manualRecalculate();
 historyPaint();}catch{status.textContent='Перенос отменён: нет свежего подтверждения котировок';}}
for(const key of ['entry','sl','tp'])manualFields[key].addEventListener('change',()=>{
 if(!copiedId)return;const v=editedLevels();
 journal.edited(copiedId,v,Date.now()/1000);manualRecalculate();historyPaint();});
clipboard.onclick=async()=>{
 if(!copiedId||!['LONG','SHORT'].includes(manualFields.direction.value))return;
 try{const latestCopy=await fetchFresh(),current=latestCopy.confidence_candidates?.find(c=>c.id===copiedId);
  if(!usable(latestCopy,current,Date.now()/1000,journal.threshold))throw Error('STALE');}
 catch{manualStatus.textContent='Котировки или гипотеза устарели. Выберите заново свежий план; копирование отменено.';return;}
 const values=editedLevels(),costs=manualRecalculate();if(!costs)return;
 if(!root.confirm('Скопировать только текст исследовательского плана? Ни один ордер не создаётся. Проверить Entry, SL, TP и риски на Bybit Demo самостоятельно?'))return;
 const plan='RESEARCH ONLY · NOT AN ORDER\nBTCUSDT Bitget USDT-M → verify on Bybit Demo\n'+manualFields.direction.value+
  '\nEntry '+values[0]+'\nSL '+values[1]+'\nTP '+values[2]+'\nModeled net RR '+costs.net_rr.toFixed(2)+
  '\nFee reserve SL/TP '+costs.stop_fees.toFixed(2)+'/'+costs.target_fees.toFixed(2)+
  ' USDT, funding reserve '+costs.funding_reserve.toFixed(2)+' USDT / 1 BTC'+
  '\nSignal Confidence is NOT win probability. No order created.';
 try{await navigator.clipboard.writeText(plan);manualStatus.textContent='Текст скопирован. Проверьте текущие Bid/Ask и риск в Bybit Demo; ордер не создан.';}
 catch{manualStatus.textContent='Буфер обмена недоступен. Значения доступны в локальных полях.';}
};
range.addEventListener('input',()=>{const n=Number(range.value);if(!validThreshold(n))return;journal.threshold=n;journal.save();value.textContent=n+'/100';paint();});
exportButton.onclick=()=>{const payload={scope:'AURA5_LOCAL_RESEARCH_SCORE_NOT_ACCOUNT_HISTORY',threshold:journal.threshold,rows:journal.rows,
 warning:'Technical score is NOT a win probability. Outcomes UNKNOWN without gap-free forward study.'};
 const u=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'})),a=document.createElement('a');
 a.href=u;a.download='aura5-signal-confidence-journal.json';a.click();URL.revokeObjectURL(u);};
async function poll(){try{if(!document.hidden){latest=await fetchFresh();paint();}}catch{latest=null;cards.replaceChildren();status.textContent='OFFLINE/STALE · баллы и перенос скрыты';}
 finally{setTimeout(poll,4000);}}
document.addEventListener('visibilitychange',()=>{if(document.hidden){latest=null;audioReady=false;player.suspend();audioButton.textContent='Включить WATCH-звук ≥ порога · только эта вкладка';cards.replaceChildren();status.textContent='PAUSED · вкладка скрыта';}
 else status.textContent='Восстановление свежих данных…';});
poll();
})(typeof window==='undefined'?globalThis:window);

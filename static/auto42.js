/* Internal virtual-only owner dashboard. No scheduler token or exchange API. */
(()=>{
 'use strict';
 const labels={OFF:'Выключено',ON:'Включено владельцем',PAUSED:'Приостановлено',ERROR:'Ошибка',EMERGENCY:'Аварийная остановка',NOT_OPERATIONAL:'НЕ РАБОТАЕТ — требуется настройка или проверка',RECENT_TICK_OBSERVED:'Недавний запуск подтверждён; непрерывность не гарантируется',STORAGE_NOT_CONFIGURED:'Настройте постоянное хранилище',SCHEDULER_NOT_CONFIGURED:'Настройте внешний scheduler',ACTIVATION_BASELINE:'Установлена стартовая свеча; входа ещё нет',NO_CONFIRMED_SETUP:'Нет подтверждённого retest',SIGNAL_QUEUED_NEXT_OPEN:'Сигнал записан; ожидается следующая свеча',POSITION_ALREADY_OPEN:'Виртуальная позиция уже открыта',DAILY_LOSS_LIMIT:'Дневной лимит потерь достигнут',DRAWDOWN_LIMIT:'Лимит общей просадки достигнут',EMERGENCY_STOP:'Новые входы запрещены аварийной остановкой',OWNER_STOP:'Остановлено владельцем',MISSING_CANDLES:'Пропуск свечей; исполнение заблокировано',STALE_DATA:'Нет свежих данных',MTF_UNAVAILABLE:'Недостаточно закрытых данных 1h/4h',MTF_NOT_ALIGNED:'Таймфреймы не согласованы',NO_CONFIRMED_STRUCTURE_BREAK:'Нет подтверждённого BOS/CHoCH',AUTO_OFF:'Новые входы выключены',OPPOSING_LEVEL_TOO_CLOSE:'Цель блокируется ближайшим уровнем',OPPOSING_LIQUIDITY:'Неоднозначная или встречная ликвидность',CONFIRMED_STRUCTURE_RETEST:'Подтверждённый retest структуры',VOLATILITY_FILTER:'Отказ фильтра волатильности',RESET_BLOCKED_OPEN_POSITION:'Сброс запрещён при открытой позиции',STOP_BEFORE_RESET:'Сначала остановите режим',EMERGENCY_RESET_REQUIRED:'Для снятия аварийного запрета нужен отдельный сброс без открытой позиции',SOURCE_CORRECTION_OR_HISTORY_MISSING:'История изменилась или отсутствует; исполнение остановлено',CATCHUP_LIMIT:'Пропущено слишком много свечей',RISK_LIMIT:'Превышен риск',CONCURRENT_UPDATE:'Состояние изменилось другим запросом; повторите после обновления',INSUFFICIENT_BALANCE:'Недостаточно виртуальных средств'};
 const label=v=>labels[v]||v||'—';
 const number=v=>v===null||v===undefined?'—':Number.isFinite(Number(v))?Number(v).toLocaleString('ru-RU',{maximumFractionDigits:4}):'—';
 const date=v=>typeof v==='number'?new Date(v*1000).toLocaleString('ru-RU',{timeZone:'UTC'})+' UTC':'—';
 function view(data,failed=false,now=Date.now()/1000){
  const s=data?.state;const fresh=data?.fresh===true&&!failed&&Number.isFinite(data.server_now)&&now>=data.server_now-30&&now-data.server_now<=120&&now-s?.last_mark_at<900&&now-s?.last_success_at<=360;const pos=s?.position;
  return {status:failed?'Нет свежих данных — сервер не ответил':label(data?.status),mode:label(s?.mode),
   balance:number(s?.balance),equity:fresh?number(data.current_equity):'Нет свежих данных',
   realized:number(s?.realized_pnl),unrealized:fresh?number(data.unrealized_pnl):'Нет свежих данных',
   trades:number(s?.trades),win:number(data?.win_rate),pf:data?.profit_factor_status==='NO_LOSSES'?'Не определён: нет убытков':number(data?.profit_factor),drawdown:number(s?.max_drawdown_pct),
   missed:`Свечи: ${number(s?.missed_candles)} · scheduler-слоты: ${number(s?.missed_runs)}`,last:label(s?.last_error||s?.last_decision||data?.reason),run:date(s?.last_success_at),candle:date(s?.watermark),
   position:pos?`${pos.direction} · вход ${number(pos.entry_price)} · размер ${number(pos.size)} BTC · SL ${number(pos.stop_loss)} · TP ${number(pos.take_profit)}`:'Нет открытой виртуальной позиции',
   canStart:!!s&&Number.isInteger(data?.revision)&&!!data?.scheduler_configured&&!s.emergency&&!s.position&&s.mode!=='ON'&&!failed,
   canStop:!!s,canReset:!!s&&!s.position&&s.mode!=='ON'};
 }
 if(typeof module!=='undefined')module.exports={view};
 if(typeof document==='undefined')return;
 const panel=document.getElementById('auto42-panel');if(!panel)return;
 const out=id=>document.getElementById('a42-'+id);let data=null,busy=false,failed=false,controller=null,closed=false,timer=null,generation=0;
 const msg=t=>{out('message').textContent=t;};
 const safeError=t=>Object.assign(new Error(t),{safe:true});
 function render(){
  const v=view(data,failed);
  for(const k of ['status','mode','balance','equity','realized','unrealized','trades','win','pf','drawdown','last','run','candle','position','missed'])out(k).textContent=v[k];
  out('start').disabled=busy||!v.canStart;out('stop').disabled=!v.canStop;out('emergency').disabled=!v.canStop;out('reset').disabled=busy||!v.canReset;out('refresh').disabled=busy;
  const list=out('history');list.replaceChildren();
  for(const t of data?.trades||[]){const li=document.createElement('li');li.textContent=`${date(t.exit_time)} · ${t.direction} · ${label(t.exit_reason)} · PnL ${number(t.realized_pnl)} USDT`;list.append(li);}
  if(!data?.trades?.length){const li=document.createElement('li');li.textContent='Закрытых сделок в последних 60 событиях нет';list.append(li);}
 }
 async function request(url,options={}){
  const local=new AbortController();controller=local;const timeout=setTimeout(()=>local.abort(),60000);
  try{
   const r=await fetch(url,{credentials:'same-origin',cache:'no-store',signal:local.signal,...options});
   if(r.status===401||r.status===403){data=null;throw safeError('Требуется вход владельца: используйте Вход владельца');}
   const body=await r.json();if(!r.ok)throw safeError(label(body.code||'ERROR'));
   if(body.paper_only!==true||body.exchange_execution!==false)throw safeError('Ответ не прошёл проверку PAPER ONLY');
   return body;
  }finally{clearTimeout(timeout);if(controller===local)controller=null;}
 }
 async function refresh(){
  if(busy||closed)return;const run=++generation;busy=true;render();
  try{const result=await request('/api/auto42/status');if(run!==generation)return;data=result;failed=false;msg(data.state?'':'Режим не настроен. Новые сделки невозможны.');}
  catch(e){if(run===generation){failed=true;msg(e.name==='AbortError'?'Время ожидания истекло; состояние не подтверждено':e.safe?e.message:'Нет свежего ответа сервера');}}
  finally{if(run===generation){busy=false;if(!closed)render();}}
 }
 async function control(action){
  const urgent=action==='STOP'||action==='EMERGENCY';
  if(closed||(busy&&!urgent))return;
  if((action==='START'||action==='RESET')&&!window.confirm(action==='START'?'Включить экспериментальную виртуальную торговлю? Преимущество не доказано. Только отдельный демобаланс.':'Создать новый демопортфель 10 000 USDT? Старый журнал сохранится.'))return;
  if(action==='EMERGENCY'&&!window.confirm('Запретить все новые входы? Защитные виртуальные выходы продолжатся только по проверенным данным.'))return;
  if(urgent&&busy)controller?.abort();
  const run=++generation;busy=true;render();
  try{
   const request_id=crypto.randomUUID().replace(/-/g,'');
   await request('/api/auto42/control',{method:'POST',headers:{'Content-Type':'application/json','X-Aura-Paper':'local-only'},body:JSON.stringify({action,request_id,confirmation:action==='START'?'START PAPER':action==='RESET'?'RESET DEMO':'',expected_revision:action==='START'?data?.revision:null})});
   if(run!==generation)return;
   const result=await request('/api/auto42/status');if(run!==generation)return;
   data=result;failed=false;msg('Сервер подтвердил действие. Проверяйте состояние и время scheduler.');
  }catch(e){if(run===generation){failed=true;msg(e.name==='AbortError'?'Исход запроса неизвестен: обновите состояние; не считайте действие выполненным':e.safe?e.message:'Сервер недоступен; исход действия не подтверждён');}}
  finally{if(run===generation){busy=false;if(!closed)render();}}
 }
 panel.addEventListener('toggle',()=>{if(panel.open)refresh();});out('refresh').addEventListener('click',refresh);
 for(const [id,action] of [['start','START'],['stop','STOP'],['emergency','EMERGENCY'],['reset','RESET']])out(id).addEventListener('click',()=>control(action));
 timer=setInterval(()=>{if(panel.open&&!document.hidden)refresh();},60000);
 document.addEventListener('visibilitychange',()=>{render();if(!document.hidden&&panel.open)refresh();});
 window.addEventListener('pagehide',()=>{closed=true;generation++;clearInterval(timer);controller?.abort();});
 // Pure display adapter exported for offline fixture tests; never activates on load.
 if(typeof module!=='undefined')module.exports={view};
 render();
})();

/* Internal virtual-only owner dashboard. No scheduler token or exchange API. */
(()=>{
 'use strict';
 const labels={OFF:'Выключено',ON:'Включено владельцем',PAUSED:'Приостановлено',ERROR:'Ошибка',EMERGENCY:'Аварийная остановка',NOT_OPERATIONAL:'НЕ РАБОТАЕТ — требуется настройка или проверка',RECENT_TICK_OBSERVED:'Недавний запуск подтверждён; непрерывность не гарантируется',STORAGE_NOT_CONFIGURED:'Настройте постоянное хранилище',SCHEDULER_NOT_CONFIGURED:'Настройте внешний scheduler',ACTIVATION_BASELINE:'Установлена стартовая свеча; входа ещё нет',NO_CONFIRMED_SETUP:'Нет подтверждённого retest',SIGNAL_QUEUED_NEXT_OPEN:'Сигнал записан; ожидается следующая свеча',POSITION_ALREADY_OPEN:'Виртуальная позиция уже открыта',DAILY_LOSS_LIMIT:'Дневной лимит потерь достигнут',DRAWDOWN_LIMIT:'Лимит общей просадки достигнут',EMERGENCY_STOP:'Новые входы запрещены аварийной остановкой',OWNER_STOP:'Остановлено владельцем',MISSING_CANDLES:'Пропуск свечей; исполнение заблокировано',STALE_DATA:'Нет свежих данных',MTF_UNAVAILABLE:'Недостаточно закрытых данных 1h/4h',MTF_NOT_ALIGNED:'Таймфреймы не согласованы',NO_CONFIRMED_STRUCTURE_BREAK:'Нет подтверждённого BOS/CHoCH',AUTO_OFF:'Новые входы выключены',OPPOSING_LEVEL_TOO_CLOSE:'Цель блокируется ближайшим уровнем',OPPOSING_LIQUIDITY:'Неоднозначная или встречная ликвидность',CONFIRMED_STRUCTURE_RETEST:'Подтверждённый retest структуры',VOLATILITY_FILTER:'Отказ фильтра волатильности',RESET_BLOCKED_OPEN_POSITION:'Сброс запрещён при открытой позиции',STOP_BEFORE_RESET:'Сначала остановите режим',EMERGENCY_RESET_REQUIRED:'Для снятия аварийного запрета нужен отдельный сброс без открытой позиции',SOURCE_CORRECTION_OR_HISTORY_MISSING:'История изменилась или отсутствует; исполнение остановлено',CATCHUP_LIMIT:'Пропущено слишком много свечей',RISK_LIMIT:'Превышен риск',CONCURRENT_UPDATE:'Состояние изменилось другим запросом; повторите после обновления',INSUFFICIENT_BALANCE:'Недостаточно виртуальных средств'};
 Object.assign(labels,{CLIENT_NO_RESPONSE:'Нет ответа в браузере; доступность сервера не подтверждена',STORAGE_NETWORK:'Сетевая ошибка хранилища',STORAGE_DNS:'DNS имени Supabase не разрешается',STORAGE_TLS:'Ошибка TLS при подключении к Supabase',STORAGE_PROXY:'Ошибка сетевого proxy до Supabase',STORAGE_CONNECT:'Не удалось установить соединение с Supabase',STORAGE_READ:'Соединение с Supabase оборвалось при чтении',STORAGE_WRITE:'Ошибка передачи запроса Supabase',STORAGE_PROTOCOL:'Некорректный сетевой ответ Supabase',STORAGE_TIMEOUT:'Превышено время ожидания Supabase',STORAGE_AUTH:'Supabase отклонил серверную авторизацию',STORAGE_PERMISSION_DENIED:'Недостаточно прав на RPC или таблицы',STORAGE_SCHEMA_MISSING:'Не найдены таблицы или RPC Aura 4.2; проверьте SQL-схему',STORAGE_DATABASE_UNAVAILABLE:'REST Supabase не может подключиться к PostgreSQL',STORAGE_RATE_LIMIT:'Лимит запросов Supabase',STORAGE_HTTP_ERROR:'Ошибка HTTP Supabase',STORAGE_REDIRECT_BLOCKED:'Перенаправление Supabase запрещено',STORAGE_INVALID_RESPONSE:'Некорректный ответ хранилища',INVALID_STORAGE_CONFIGURATION:'Неверный формат конфигурации Supabase',REQUEST_TIMEOUT:'Время проверки запроса истекло; обновите состояние перед повтором',UPSTREAM_TIMEOUT:'Binance не ответил вовремя',ANALYSIS_TIMEOUT:'Анализ не завершён в установленный срок; запуск не подтверждён'});
 const label=v=>labels[v]||v||'—';
 const number=v=>v===null||v===undefined?'—':Number.isFinite(Number(v))?Number(v).toLocaleString('ru-RU',{maximumFractionDigits:4}):'—';
 const date=v=>typeof v==='number'?new Date(v*1000).toLocaleString('ru-RU',{timeZone:'UTC'})+' UTC':'—';
 function view(data,failed=false,now=Date.now()/1000){
  const s=data?.state;const fresh=data?.fresh===true&&!failed&&Number.isFinite(data.server_now)&&now>=data.server_now-30&&now-data.server_now<=120&&now-s?.last_mark_at<900&&now-s?.last_success_at<=360;const pos=s?.position;
  return {status:failed?(data?.diagnostics?.render_api==='ONLINE'?'API ответил; данные портфеля не подтверждены':'Нет свежих данных — сервер не ответил'):label(data?.status),mode:label(s?.mode),
   balance:number(s?.balance),equity:fresh?number(data.current_equity):'Нет свежих данных',
   realized:number(s?.realized_pnl),unrealized:fresh?number(data.unrealized_pnl):'Нет свежих данных',
   trades:number(s?.trades),win:number(data?.win_rate),pf:data?.profit_factor_status==='NO_LOSSES'?'Не определён: нет убытков':number(data?.profit_factor),drawdown:number(s?.max_drawdown_pct),
   missed:`Свечи: ${number(s?.missed_candles)} · scheduler-слоты: ${number(s?.missed_runs)}`,last:label(s?.last_error||s?.last_decision||data?.reason),run:date(s?.last_success_at),candle:date(s?.watermark),
   position:pos?`${pos.direction} · вход ${number(pos.entry_price)} · размер ${number(pos.size)} BTC · SL ${number(pos.stop_loss)} · TP ${number(pos.take_profit)}`:'Нет открытой виртуальной позиции',
   canStart:!!s&&Number.isInteger(data?.revision)&&!!data?.scheduler_configured&&!s.emergency&&!s.position&&s.mode!=='ON'&&!failed,
   canStop:!!s,canReset:!!s&&!s.position&&s.mode!=='ON'};
 }
 function system(data,failed=false,transport='reply',now=Date.now()/1000){
  const d=data?.diagnostics;const recent=d&&Number.isFinite(d.checked_at)&&now>=d.checked_at-30&&now-d.checked_at<=120;
  const available=recent&&transport==='reply';const st=d?.storage;
  return {api:available&&d.render_api==='ONLINE'?'ONLINE':'UNKNOWN — нет подтверждённого ответа',
   storage:available&&['CONNECTED','ERROR'].includes(st?.status)?st.status+(st.error_code?' · '+label(st.error_code):''):'UNKNOWN',
   host:typeof st?.connection?.hostname==='string'&&/^[a-z0-9]{12,40}\.supabase\.co$/.test(st.connection.hostname)?st.connection.hostname:'—',
   category:st?.error_category||'—',
   scheduler:date(d?.scheduler_last_confirmed_at),candle:date(d?.last_processed_closed_at),
   decision:label(d?.last_decision),error:label(d?.last_error||st?.error_code),saved:date(d?.last_saved_at),
   mode:available?d.owner_mode||d.auto_paper||'UNKNOWN':'UNKNOWN',
   protection:available?(failed?'BLOCKED':d.protection||'UNKNOWN'):'UNKNOWN',
   block:available?label(d.block_reason):'Нет свежей диагностики',
   config:[...(d?.configuration?.missing_variables||[]),...(d?.configuration?.invalid_variables||[])].filter(v=>typeof v==='string'&&/^AURA_[A-Z0-9_]+$/.test(v)).join(', ')||'—'};
 }
 if(typeof module!=='undefined')module.exports={view,system};
 if(typeof document==='undefined')return;
 const panel=document.getElementById('auto42-panel');if(!panel)return;
 const out=id=>document.getElementById('a42-'+id);let data=null,busy=false,failed=false,controller=null,closed=false,timer=null,generation=0,transport='unknown';
 const msg=t=>{out('message').textContent=t;};
 const safeError=(t,body)=>Object.assign(new Error(t),{safe:true,body});
 function failure(e){failed=true;transport=e.body?.diagnostics?'reply':'unknown';if(e.body?.diagnostics)data={...(data||{}),...(e.body.state?e.body:{}),diagnostics:e.body.diagnostics};else if(data)data={...data,diagnostics:{...(data.diagnostics||{}),render_api:'UNKNOWN',storage:{status:'UNKNOWN'},checked_at:null,last_error:'CLIENT_NO_RESPONSE'}};}
 function render(){
  const v=view(data,failed);const health=system(data,failed,transport);
  for(const [id,value] of Object.entries(health))out('sys-'+id).textContent=value;
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
   const body=await r.json();if(!r.ok)throw safeError(label(body.code||'ERROR'),body);
   if(body.paper_only!==true||body.exchange_execution!==false)throw safeError('Ответ не прошёл проверку PAPER ONLY');
   return body;
  }finally{clearTimeout(timeout);if(controller===local)controller=null;}
 }
 async function refresh(){
  if(busy||closed)return;const run=++generation;busy=true;render();
  try{const result=await request('/api/auto42/status');if(run!==generation)return;data=result;failed=false;transport='reply';msg(data.diagnostics?.activation_error?'Последний START отклонён: '+label(data.diagnostics.activation_error.code)+'. Режим: '+label(data.state?.mode):data.state?'':'Режим не настроен. Новые сделки невозможны.');}
  catch(e){if(run===generation){failure(e);msg(e.name==='AbortError'?'Время ожидания истекло; состояние не подтверждено':e.safe?e.message:'Нет свежего ответа сервера');}}
  finally{if(run===generation){busy=false;if(!closed)render();}}
 }
 async function control(action){
  const urgent=action==='STOP'||action==='EMERGENCY';
  if(closed||(busy&&!urgent))return;
  if((action==='START'||action==='RESET')&&!window.confirm(action==='START'?'Включить Aura Auto Paper 4.2 — отдельный портфель Supabase, BTCUSDT 15m? Прежний Historical Pattern не изменится. Преимущество не доказано. Только виртуальные средства.':'Создать новый демопортфель 10 000 USDT? Старый журнал сохранится.'))return;
  if(action==='EMERGENCY'&&!window.confirm('Запретить все новые входы? Защитные виртуальные выходы продолжатся только по проверенным данным.'))return;
  if(urgent&&busy)controller?.abort();
  const run=++generation;busy=true;render();
  try{
   const request_id=crypto.randomUUID().replace(/-/g,'');
   await request('/api/auto42/control',{method:'POST',headers:{'Content-Type':'application/json','X-Aura-Paper':'local-only'},body:JSON.stringify({action,request_id,confirmation:action==='START'?'START PAPER':action==='RESET'?'RESET DEMO':'',expected_revision:action==='START'?data?.revision:null})});
   if(run!==generation)return;
   const result=await request('/api/auto42/status');if(run!==generation)return;
   data=result;failed=false;transport='reply';msg('Сервер подтвердил действие. Проверяйте состояние и время scheduler.');
  }catch(e){if(run===generation){failure(e);msg(e.name==='AbortError'?'Исход запроса неизвестен: обновите состояние; не считайте действие выполненным':e.safe?(action==='START'&&e.body?.state?.mode==='OFF'&&e.body?.diagnostics?.activation_error?.code===e.body?.code?'Запуск отклонён, режим остался OFF. ':'')+e.message:'Сервер недоступен; исход действия не подтверждён');}}
  finally{if(run===generation){busy=false;if(!closed)render();}}
 }
 panel.addEventListener('toggle',()=>{if(panel.open)refresh();});out('refresh').addEventListener('click',refresh);
 for(const [id,action] of [['start','START'],['stop','STOP'],['emergency','EMERGENCY'],['reset','RESET']])out(id).addEventListener('click',()=>control(action));
 timer=setInterval(()=>{if(panel.open&&!document.hidden)refresh();},60000);
 document.addEventListener('visibilitychange',()=>{render();if(!document.hidden&&panel.open)refresh();});
 window.addEventListener('pagehide',()=>{closed=true;generation++;clearInterval(timer);controller?.abort();});
 // Pure display adapter exported for offline fixture tests; never activates on load.
 if(typeof module!=='undefined')module.exports={view,system};
 render();
 if(panel.open)refresh(); // Read-only owner status; never activates on page load.
})();

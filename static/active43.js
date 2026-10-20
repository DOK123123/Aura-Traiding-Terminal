/* Isolated owner UI. All operations are virtual; never manufactures a signal. */
(function(){'use strict';
 const labels={ON:'Включён',OFF:'Выключен',PAUSED:'Приостановлен',EMERGENCY:'Аварийный запрет входов',ERROR:'Ошибка',
 ACTIVE43_BITGET_DISABLED:'Bitget Futures выключен отдельной настройкой сервера',ACTIVE43_DISABLED:'Режим выключен в настройках сервера',ACTIVE43_STORAGE_NOT_CONFIGURED:'Отдельное хранилище Aura 4.3 не настроено',ACTIVE43_NOT_CONFIGURED:'Aura 4.3 не настроена',
 NO_CONFIRMED_TICK:'Сохранённых успешных циклов ещё нет',STALE_TICK:'Последний успешный цикл устарел',DIAGNOSTIC_TIMEOUT:'Проверка превысила лимит времени',STORAGE_PERMISSION_DENIED:'БД запретила чтение отдельной таблицы Aura 4.3',STORAGE_AUTH:'Supabase отклонила серверный ключ',
 NOT_STARTED:'Автоматический режим ещё не запускался',INVALID_DATA:'Источник вернул некорректные значения свечей',INVALID_MARKET_DATA:'Рыночные данные не прошли проверку',SOURCE_MISMATCH:'Источник не соответствует BITGET · BTCUSDT USDT-M Futures',
 QUOTE_SOURCE_MISMATCH:'Котировка другого источника отклонена',STALE_QUOTE:'Котировка устарела',FUTURES_NOT_VALIDATED:'Стратегия Futures ещё не прошла независимую проверку',
 NO_SIGNAL:'Нет сигнала',NO_CONFIRMED_SETUP:'Нет подтверждённого входа',WARMUP:'Недостаточно истории',WARMUP_OR_FLAT_ATR:'Прогрев или нулевой ATR',
 ACTIVATION_BASELINE:'Запущен со свежей свечи; ожидается новый сигнал',SIGNAL_QUEUED_NEXT_OPEN:'Сигнал сохранён; ожидается следующая закрытая свеча',
 POSITION_ALREADY_OPEN:'Позиция уже открыта',AUTO_OFF:'Новые входы выключены',OWNER_STOP:'Остановлено владельцем',
 MARKET_UNAVAILABLE:'Источник свечей недоступен',STALE_DATA:'Свечи устарели',STALE_OR_MISMATCHED_DATA:'Время или целостность данных не подтверждены',
 FUTURES_FILTERS_UNAVAILABLE:'Не удалось проверить ограничения Bitget Futures',FUTURES_FILTERS_CHANGED:'Параметры контракта Bitget изменились; новые входы запрещены',
 REGION_OR_ACCESS_RESTRICTED:'Bitget недоступен из региона сервера (403/451); входы запрещены',RATE_LIMIT:'Bitget ограничил частоту запросов; входы приостановлены',
 UPSTREAM_TIMEOUT:'Bitget не ответил вовремя',NETWORK_ERROR:'Нет соединения с Bitget',UPSTREAM_CLOCK_OR_STALE_RESPONSE:'Часы Bitget или ответ не прошли проверку свежести',
 NEVER_SEEN:'Циклы ещё не поступали',NOT_CONFIGURED:'Scheduler не настроен',FRESH:'Недавний цикл подтверждён в БД',STALE:'Циклы не поступают; проверьте scheduler и Render',
 SOURCE_CORRECTION_OR_HISTORY_MISSING:'История изменилась или отсутствует; требуется проверка',MISSING_CANDLES:'Пропущены свечи',INCOMPLETE_HISTORY:'История неполная',
 STORAGE_UNAVAILABLE_OUTCOME_UNKNOWN:'БД недоступна; исход операции не подтверждён',STORAGE_TIMEOUT_OUTCOME_UNKNOWN:'БД не ответила; исход операции неизвестен',
 STORAGE_READBACK_OUTCOME_UNKNOWN:'Не подтверждено повторное чтение записи',STORAGE_SCHEMA_MISSING:'Примените отдельную SQL-схему Aura 4.3',
 SCHEDULER_NOT_CONFIGURED:'Отдельный scheduler не настроен',DAILY_LOSS_LIMIT:'Дневной лимит убытка 2%',DRAWDOWN_LIMIT:'Лимит просадки 10%',
 CONFIG_CHANGED:'Конфигурация не совпадает с сохранённым портфелем',CONCURRENT_UPDATE:'Состояние изменилось; обновите панель',ALREADY_ON:'Режим уже включён',
 EMERGENCY_STOP:'Аварийный запрет входов',OPEN_POSITION_REQUIRES_PROTECTIVE_TICK:'Сначала требуется защитная обработка открытой позиции',
 INVALID_STOPS_AT_NEXT_OPEN:'Следующая цена не соответствует SL/TP',MINIMUM_SIZE_OR_NOTIONAL:'Недостаточный размер позиции',
 NO_VOLATILITY_COMPRESSION:'Нет подтверждённого сжатия волатильности',VOLUME_FILTER:'Объём не подтверждает вход',ADX_FILTER:'Недостаточная сила тренда',
 STOP_LOSS:'Stop Loss',TAKE_PROFIT:'Take Profit',STOP_LOSS_AMBIGUOUS:'SL и TP одной свечой: учтён SL',STOP_GAP:'Stop Loss с ценовым разрывом',
 TAKE_PROFIT_GAP_CONSERVATIVE:'TP при разрыве, консервативно',STRATEGY_EXIT_NEXT_OPEN:'Выход по стратегии на следующем open',
 COLD_START:'Новое хранилище',OWNER_STARTED:'Запущено владельцем',DATA_BLOCKED:'Восстановление блокируется данными',
 POSITION_RESTORED:'Позиция восстановлена из БД',FRESH_DATA_RECOVERED:'Свежие данные восстановлены'};
 const label=x=>labels[x]||x||'—';
 const num=x=>x!==null&&x!==undefined&&x!==''&&Number.isFinite(Number(x))?Number(x).toLocaleString('ru-RU',{maximumFractionDigits:5}):'—';
 const date=x=>typeof x==='number'?new Date(x*1000).toLocaleString('ru-RU',{timeZone:'UTC'})+' UTC':'—';
 function view(data,failed=false,now=Date.now()/1000){
  if(data?.state&&(data.market_source!=='Bitget · USDT-M Futures / api.bitget.com'||data.state.market_source!==data.market_source||data.state.strategy_version!=='AURA_4.3_ACTIVE_PAPER_3'))return view(null,true,now);
  const s=data?.state,p=s?.position;const step={'5m':300,'15m':900,'1h':3600,'4h':14400}[s?.config?.timeframe];
  const fresh=!failed&&data?.current_equity!==null&&Number.isFinite(data?.server_now)&&now>=data.server_now-30&&now-data.server_now<120&&Number.isFinite(s?.last_mark_at)&&now-s.last_mark_at<step&&now-s.last_mark_at>=0&&Number.isFinite(s?.last_success_at)&&now-s.last_success_at<360&&now-s.last_success_at>=0&&!s?.last_error;
  return {mode:failed?'Состояние не подтверждено':label(s?.mode),market:fresh?'Свежие закрытые свечи':'Нет свежего подтверждения рынка',
   storage:!failed&&data?.storage_status==='CONNECTED'?'Supabase: подтверждено чтение':'Supabase: не подтверждена',
   strategy:s?.config?`${s.config.strategy} ${s.config.timeframe} · BITGET · BTCUSDT USDT-M Futures · PAPER`:'—',
   candle:date(s?.watermark),run:date(s?.last_run_at),saved:date(data?.last_saved_at),
   success:date(data?.last_market_success_at),successfulrun:date(data?.last_successful_run_at),scheduler:failed?'Состояние scheduler не подтверждено':label(data?.scheduler_status==='FRESH'&&(!Number.isFinite(s?.last_run_at)||now-s.last_run_at>360)?'STALE':data?.scheduler_status),
   signal:s?.last_signal?`${s.last_signal.direction} · ${date(s.last_signal.signal_at)} · ${label(s.last_signal.reason)}`:'Подтверждённых сигналов ещё нет',
   reason:label(s?.last_error||s?.last_decision||data?.code),balance:num(s?.balance),equity:fresh?num(data.current_equity):'Нет свежих данных',
   realized:num(s?.realized_pnl),pnl:p?(fresh?num(data.position_net_pnl):'Нет свежих данных'):'—',fees:num(s?.fees),slippage:num(s?.slippage),
   drawdown:num(s?.max_drawdown_pct),count:num(s?.trades),win:num(data?.win_rate),recovery:data?.restart_readback?label(s?.recovery_status):'Чтение после старта не подтверждено',
   position:p?`${p.direction} · ${num(p.size)} BTC · вход ${num(p.entry_price)} · SL ${num(p.active_stop||p.stop_loss)} · TP ${num(p.take_profit)} · ${date(p.entry_time)}`:'Нет открытой позиции',
   live:s?.monitor_error?'Диагностика цикла недоступна; проверьте журнал сделок':data?.production_paper_verified===true?'Зафиксирован реальный Render/Supabase цикл':'WAITING_FOR_REAL_SIGNAL — автономный production-цикл не подтверждён',
   canStart:!!s&&!failed&&s.mode!=='ON'&&!s.emergency&&!p&&!!data.scheduler_configured&&Number.isInteger(data.revision),canStop:!!s};
 }
 function chartModel(data){
  const chart=data?.chart,step={'5m':300,'15m':900,'1h':3600,'4h':14400}[chart?.timeframe];
  if(chart?.source!=='Bitget · USDT-M Futures / api.bitget.com'||!step||!Array.isArray(chart.bars)||chart.bars.length<2||chart.bars.length>120)return null;
  const bars=chart.bars;if(bars.some((b,i)=>!Number.isInteger(b.time)||b.time%step||b.time+step>chart.closed_at||i&&b.time-bars[i-1].time!==step||['open','high','low','close'].some(k=>!Number.isFinite(Number(b[k]))||Number(b[k])<=0)||Number(b.low)>Math.min(Number(b.open),Number(b.close))||Number(b.high)<Math.max(Number(b.open),Number(b.close))))return null;
  const first=bars[0].time,last=bars.at(-1).time+step,marks=[];
  for(const t of data.trades||[]){if(t.market_source!==chart.source)continue;for(const [at,price,text] of [[t.entry_time,t.entry_price,'OPEN '+t.direction],[t.exit_time,t.exit_price,'CLOSE '+t.exit_reason]])if(Number.isFinite(at)&&at>=first&&at<=last&&Number(price)>0)marks.push({at,price:Number(price),text});}
  const p=data.state?.position;
  if(p?.market_source===chart.source&&p.entry_time>=first&&p.entry_time<=last)marks.push({at:p.entry_time,price:Number(p.entry_price),text:'OPEN '+p.direction});
  return {bars,marks,step,first,last,closed:chart.closed_at};
 }
 if(typeof module!=='undefined')module.exports={view,label,chartModel};
 if(typeof document==='undefined')return;
 const panel=document.getElementById('active43-panel');if(!panel)return;
 const out=k=>document.getElementById('a43-'+k);let data=null,busy=false,failed=false,closed=false,generation=0,controller=null,quoteController=null,quoteExpiry=null;
 function render(){
  const v=view(data,failed);
  for(const k of ['mode','market','storage','strategy','candle','run','saved','signal','reason','balance','equity','realized','pnl','fees','slippage','drawdown','count','win','recovery','position','live','scheduler','success','successfulrun'])out(k).textContent=v[k];
  out('start').disabled=busy||!v.canStart;out('stop').disabled=!v.canStop;out('emergency').disabled=!v.canStop;out('refresh').disabled=busy;
  out('older').disabled=busy||!data?.history_has_more||!data?.history_cursor;
  out('history').replaceChildren();for(const t of data?.trades||[]){const row=document.createElement('li');row.textContent=`${date(t.exit_time)} · ${t.direction} · ${label(t.exit_reason)} · вход ${num(t.entry_price)} → выход ${num(t.exit_price)} · SL ${num(t.stop_loss)} / TP ${num(t.take_profit)} · ${num(t.realized_pnl)} USDT · комиссии ${num(t.fees)} · ${label(t.reason)}`;out('history').append(row);}
  drawChart();
  if(!data?.trades?.length){const row=document.createElement('li');row.textContent=data?.state?'В текущем портфеле закрытых сделок нет':'История не загружена';out('history').append(row);}
 }

 function drawChart(){
  const svg=out('chart');if(!svg||typeof document.createElementNS!=='function')return;
  svg.replaceChildren();const model=chartModel(data);
  out('chart-status').textContent=model?'Bitget Futures · только закрытые свечи · '+date(model.closed)+(Date.now()/1000-model.closed>900?' · данные могут быть устаревшими':''):'График появится после сохранённого scheduler-цикла; Spot-данные не подставляются.';
  if(!model)return;const {bars,marks,first,last,step}=model,ns='http://www.w3.org/2000/svg';
  const levels=[...bars.flatMap(b=>[Number(b.low),Number(b.high)]),...marks.map(m=>m.price)],low=Math.min(...levels),high=Math.max(...levels),span=high-low||1;
  const x=t=>12+(t-first)/(last-first)*826,y=p=>210-(p-low)/span*190;
  function add(name,attrs,title){const e=document.createElementNS(ns,name);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));if(title){const t=document.createElementNS(ns,'title');t.textContent=title;e.append(t);}svg.append(e);}
  for(const b of bars){const color=Number(b.close)>=Number(b.open)?'#42d6b0':'#fa788b';add('line',{x1:x(b.time+step/2),x2:x(b.time+step/2),y1:y(Number(b.high)),y2:y(Number(b.low)),stroke:color});add('line',{x1:x(b.time+step/2),x2:x(b.time+step/2),y1:y(Number(b.open)),y2:y(Number(b.close)),stroke:color,'stroke-width':Math.max(1,600/bars.length)});}
  for(const m of marks)add('circle',{cx:x(m.at),cy:y(m.price),r:4,fill:m.text.startsWith('OPEN')?'#7cbaff':'#ffd478'},m.text+' · '+num(m.price)+' · '+date(m.at));
 }
 async function request(path,options={}){
  const local=new AbortController();controller=local;const timer=setTimeout(()=>local.abort(),55000);
  try{
   const r=await fetch('/api/active43/'+path,{credentials:'same-origin',cache:'no-store',signal:local.signal,...options});
   if(r.status===401||r.status===403){data=null;throw Error('Требуется вход владельца');}
   let b;try{b=await r.json();}catch{throw Error('Сервер вернул не JSON (HTTP '+r.status+')');}
   if(!r.ok)throw Error(r.status===404?'Aura 4.3 Bitget не установлена на этом сервере (HTTP 404)':b.code?label(b.code):'Сервер не подтвердил запрос (HTTP '+r.status+')');
   if(b.paper_only!==true||b.exchange_execution!==false)throw Error('Ответ не подтверждает PAPER ONLY');
   if(path==='status'&&(b.market_source!=='Bitget · USDT-M Futures / api.bitget.com'||b.state?.market_source!==b.market_source||b.state?.strategy_version!=='AURA_4.3_ACTIVE_PAPER_3'))throw Error('Источник или версия сервера не соответствуют Aura 4.3 Bitget Futures');return b;
  }finally{clearTimeout(timer);if(controller===local)controller=null;}
 }
 async function quote(){
  if(closed||failed||!data?.state||quoteController)return;
  const local=new AbortController();quoteController=local;const timer=setTimeout(()=>local.abort(),5000);clearTimeout(quoteExpiry);out('quote').textContent='Нет свежей котировки';out('quote-pnl').textContent='Нет свежих данных';
  try{
   const r=await fetch('/api/active43/quote',{credentials:'same-origin',cache:'no-store',signal:local.signal});if(!r.ok)return;
   const b=await r.json(),q=b.quote,age=Date.now()-q?.time_ms;
   if(!closed&&b.paper_only===true&&b.exchange_execution===false&&q?.source==='Bitget · USDT-M Futures / api.bitget.com'&&q?.identity?.market_type==='USDT_PERPETUAL'&&Number(q.price)>0&&Number.isFinite(age)&&age>=-1000&&age<10000){
    out('quote').textContent=num(q.price)+' USDT · '+date(q.time_ms/1000);
    out('quote-pnl').textContent=b.position_id===data?.state?.position?.id?num(b.position_net_pnl_at_quote):b.position_id==null&&!data?.state?.position?'—':'Позиция изменилась; обновите панель';
    quoteExpiry=setTimeout(()=>{out('quote').textContent='Нет свежей котировки';out('quote-pnl').textContent='Нет свежих данных';},Math.max(1,10000-age));
   }
  }catch(e){/* Public display only; no financial writes. */}finally{clearTimeout(timer);quoteController=null;}
 }
 async function refresh(){
  if(busy||closed)return;const run=++generation;busy=true;render();
  try{const b=await request('status');if(run!==generation)return;data=b;failed=false;out('message').textContent='Портфель прочитан из отдельного хранилища Aura 4.3.';}
  catch(e){if(run===generation){failed=true;out('message').textContent=e.name==='AbortError'?'Сервер не ответил; состояние не подтверждено':e.message;}}
  finally{if(run===generation){busy=false;if(!closed){render();if(!failed)quote();}}}
 }
 async function control(action){
  const urgent=action!=='START';if(closed||(busy&&!urgent))return;
  if(!window.confirm(action==='START'?'Включить виртуальную Aura 4.3 Bitget Futures? Стратегия не имеет подтверждённого преимущества. Возможны виртуальные убытки. Только отдельный PAPER-портфель.':action==='STOP'?'Запретить новые входы Aura 4.3? Защитные выходы требуют работающего scheduler.':'Установить аварийный запрет входов Aura 4.3? Автоматически он не снимается.'))return;
  if(urgent)controller?.abort();const run=++generation;busy=true;render();
  try{
   await request('control',{method:'POST',headers:{'Content-Type':'application/json','X-Aura-Paper':'local-only'},body:JSON.stringify({action,request_id:crypto.randomUUID().replace(/-/g,''),expected_revision:action==='START'?data?.revision:null,confirmation:action==='START'?'START EXPERIMENTAL PAPER':''})});
   if(run!==generation)return;const b=await request('status');if(run!==generation)return;data=b;failed=false;out('message').textContent='Действие подтверждено. Проверяйте режим, scheduler и сохранённые события.';
  }catch(e){if(run===generation){failed=true;out('message').textContent='Действие не подтверждено: '+(e.name==='AbortError'?'обновите состояние перед повтором':e.message);}}
  finally{if(run===generation){busy=false;if(!closed)render();}}
 }
 let diagnosticBusy=false;
 out('diagnose').addEventListener('click',async()=>{
  if(closed||diagnosticBusy)return;diagnosticBusy=true;out('diagnose').disabled=true;
  for(const k of ['bitget','storage','scheduler'])out('diag-'+k).textContent='Проверяется…';
  for(const k of ['tick','balance','position','at','error'])out('diag-'+k).textContent='—';
  out('diagnostic-message').textContent='Проверка с сервера, без торговых операций…';
  try{
   const b=await request('diagnostics',{method:'POST',headers:{'X-Aura-Paper':'local-only'}});
   if(b.read_only!==true||b.state_changed!==false||b.market_source!=='Bitget · USDT-M Futures / api.bitget.com'||b.strategy_version!=='AURA_4.3_ACTIVE_PAPER_3')throw Error('Сервер не подтвердил безопасную диагностику Bitget');
   out('diag-bitget').textContent=b.bitget.status+(b.bitget.code?' · '+label(b.bitget.code):' · '+num(b.bitget.price)+' USDT · '+date(b.bitget.quote_at_ms/1000)+' · закрытые 15m/1h/4h');
   out('diag-storage').textContent=b.supabase.status+(b.supabase.code?' · '+label(b.supabase.code):b.supabase.account_status==='NOT_INITIALIZED'?' · счёт ещё не создан (проверка его не создаёт)':' · чтение RPC и портфеля подтверждено');
   out('diag-scheduler').textContent=b.scheduler.status+(b.scheduler.code?' · '+label(b.scheduler.code):' · недавний сохранённый успешный tick');
   out('diag-tick').textContent=date(b.scheduler.last_successful_tick);
   out('diag-balance').textContent=num(b.virtual_balance);
   const p=b.current_position;out('diag-position').textContent=p?`${p.direction} · ${num(p.size)} BTC · Entry ${num(p.entry_price)} · SL ${num(p.active_stop||p.stop_loss)} · TP ${num(p.take_profit)}`:b.virtual_balance===null?'Не подтверждена':'Нет открытой позиции';
   out('diag-at').textContent=date(b.checked_at);
   out('diag-error').textContent=(b.errors||[]).map(label).join('; ')||'Нет';
   out('diagnostic-message').textContent=(b.checked_on_render?'Проверено на Render':'Проверено на сервере приложения; Render не подтверждён')+' · '+b.status+' · PAPER не включался. '+
    (b.configuration.server_enabled?'Серверный модуль разрешён. ':'Серверный модуль выключен. ')+
    (b.configuration.missing_variables.length?'Отсутствуют: '+b.configuration.missing_variables.join(', ')+'. ':'')+
    (b.configuration.explicit_global_stop?'AURA_ACTIVE43_ENABLED явно выключен; требуется разрешение владельца на включение. ':'');
  }catch(e){
   for(const k of ['bitget','storage','scheduler'])out('diag-'+k).textContent='ERROR · не подтверждено';
   out('diagnostic-message').textContent='Диагностика не подтверждена: '+(e.name==='AbortError'?'тайм-аут сервера':e.message);
  }finally{diagnosticBusy=false;out('diagnose').disabled=false;}
 });
 out('refresh').addEventListener('click',refresh);for(const [id,action] of [['start','START'],['stop','STOP'],['emergency','EMERGENCY']])out(id).addEventListener('click',()=>control(action));
 out('older').addEventListener('click',async()=>{
  if(busy||!data?.history_cursor)return;const run=++generation,epoch=data.state.epoch;busy=true;render();
  try{const b=await request('trades?before='+data.history_cursor);if(run!==generation)return;if(b.epoch!==epoch)throw Error('Портфель изменился; обновите панель');data={...data,trades:[...data.trades,...b.trades],history_cursor:b.next_cursor,history_has_more:b.page_may_have_more};}
  catch(e){if(run===generation)out('message').textContent='История не загружена: '+e.message;}
  finally{if(run===generation){busy=false;if(!closed)render();}}
 });
 panel.addEventListener('toggle',()=>{if(panel.open)refresh();});
 const poll=setInterval(()=>{render();if(panel.open&&!document.hidden)refresh();},30000);
 const quotes=setInterval(()=>{if(panel.open&&!document.hidden)quote();},5000);
 document.addEventListener('visibilitychange',()=>{render();if(!document.hidden&&panel.open)refresh();});
 window.addEventListener('pagehide',()=>{closed=true;generation++;clearInterval(poll);clearInterval(quotes);clearTimeout(quoteExpiry);controller?.abort();quoteController?.abort();});
 // Historical results are a separate public, immutable artifact. Never written
 // to the live ledger; a browser cannot invoke research or select a live model.
 out('research').addEventListener('click',async()=>{
  out('research').disabled=true;
  try{
   const r=await fetch('/static/active43-research.json',{cache:'no-store'});if(!r.ok)throw Error();const b=await r.json();
   if(b.production_paper_verified!==false||b.no_profitability_claim!==true)throw Error();
   out('research-status').textContent='АРХИВ SPOT, НЕ BITGET FUTURES И НЕ LIVE · '+b.verdict+' · Binance Spot · 60/20/20 · повторно использованные периоды требуют нового forward-теста';
   out('comparison').replaceChildren();
   for(const row of b.candidates){const m=row.full_year.metrics,v=row.validation.metrics,t=row.final_test.metrics,tr=document.createElement('tr');
    const cells=[row.config.strategy,row.config.timeframe,m.trades,m.trades_per_week,m.net_profit,m.return_pct,m.win_rate,m.profit_factor,m.max_drawdown_pct,m.expectancy,m.sharpe,m.average_win,m.average_loss,m.mean_duration_hours,m.total_fees,m.fees_to_abs_gross_pct,v.net_profit,t.net_profit,t.trades];
    for(const value of cells){const td=document.createElement('td');td.textContent=typeof value==='string'&&Number.isNaN(Number(value))?value:num(value);tr.append(td);}out('comparison').append(tr);
   }
   const chosen=b.candidates.find(x=>x.config.strategy===b.selection.config.strategy&&x.config.timeframe===b.selection.config.timeframe);const curve=chosen.daily_equity;
   const canvas=out('curve'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);const values=curve.map(p=>Number(p.equity)),min=Math.min(...values),max=Math.max(...values);ctx.beginPath();ctx.strokeStyle='#27c6a5';ctx.lineWidth=2;
   values.forEach((n,i)=>{const x=10+i*(canvas.width-20)/Math.max(1,values.length-1),y=canvas.height-10-(n-min)*(canvas.height-20)/Math.max(1,max-min);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);});ctx.stroke();
   out('curve-label').textContent=`Историческая equity ${chosen.config.strategy} ${chosen.config.timeframe}: ${num(min)}…${num(max)} USDT. Отдельный годовой backtest, не баланс текущего Paper.`;
  }catch(e){out('research-status').textContent='Исторический отчёт не загружен; результаты не подменяются демонстрацией';}
  finally{out('research').disabled=false;}
 });
 render();if(panel.open)refresh();
})();

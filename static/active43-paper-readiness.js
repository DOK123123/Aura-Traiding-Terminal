/* Owner-only read probe; no controls, tick or account writes. */
(function(){'use strict';
 const SOURCE='Bitget · USDT-M Futures / api.bitget.com';
 const utc=x=>Number.isInteger(x)&&x>0?new Date(x*1000).toISOString():'Не подтверждено';
 const label={AUTO_OFF:'PAPER выключен',BOUNCE_NO_CONFIRMED_REJECTION:'Нет подтверждённого отскока',BOUNCE_WARMUP:'Недостаточный прогрев',PAPER_NOT_OFF:'Для подготовки нужен PAPER OFF',SR_BOUNCE_5M_NOT_SELECTED:'Не выбрана SR_BOUNCE 5m',TWO_RECENT_AUTOMATIC_OFF_TICKS_NOT_CONFIRMED:'Нет двух подтверждённых автоматических OFF-циклов; старый Worker не сохраняет источник запуска',ACCOUNT_CHANGED_DURING_READ:'Счёт изменился во время чтения — повторите проверку',FRESH_5M_SNAPSHOT_NOT_CONFIRMED:'Свежие данные 5m не подтверждены',MARKET_SNAPSHOT_EXPIRED:'Снимок свечей устарел',READINESS_READ_FAILED:'Ошибка чтения или неполный ответ',SCHEDULER_ACCOUNT_NOT_INITIALIZED:'Счёт не инициализирован',HISTORY_CANDLE_CHANGED:'Контрольная свеча отличается от сохранённой',HISTORY_CANDLE_MISSING:'Контрольная свеча отсутствует в доступной истории',HISTORY_INCOMPLETE:'Нарушена непрерывность истории',HISTORY_NOT_CHECKED:'История относительно якоря не проверена',MATCHED:'Сохранённый контрольный хеш совпадает',NOT_ESTABLISHED:'Якорь ещё не установлен; только новый OFF-счёт',NUMERIC_VALUES_CHANGED:'Изменились числовые значения OHLCV',DECIMAL_FORMAT_CHANGED:'Изменилось представление Decimal; проверяется точное числовое равенство' };
 const code=x=>typeof x==='string'&&/^[A-Z0-9_]{1,100}$/.test(x)?(label[x]||x):'Не подтверждено';
 const flag=x=>typeof x==='boolean'?(x?'Есть':'Нет'):'Не подтверждено';
 const amount=x=>typeof x==='string'&&/^-?\d{1,20}(\.\d{1,12})?$/.test(x)?x:'Не подтверждено';
 function view(b,now=Date.now()/1000){
  const fail={status:'BLOCKED',text:'Нет свежего подтверждённого ответа. Войдите владельцем и повторите проверку.'};
  if(!b||b.scope!=='AURA43_ACTIVE_PAPER'||b.market_source!==SOURCE||b.strategy_version!=='AURA_4.3_ACTIVE_PAPER_3'||b.purpose!=='PAPER_START_READINESS'||b.read_only!==true||b.state_changed!==false||b.paper_only!==true||b.exchange_execution!==false||b.production_paper_verified!==false||!Number.isInteger(b.checked_at)||now-b.checked_at>60||now-b.checked_at< -3||!Array.isArray(b.errors))return fail;
  const a=b.account,m=b.market,s=b.scheduler,g=b.signal,h=b.history;
  const ticks=Array.isArray(s?.ticks)?s.ticks:[];
  const validTick=t=>t&&/^ACTIVE43_BITGET_[a-f0-9]{32}:tick:[0-9]{1,12}$/.test(t.tick_id)&&t.status==='COMPLETED'&&t.mode==='OFF'&&t.state_saved===true&&t.opened===0&&t.closed===0&&Number.isInteger(t.scheduled_at)&&Number.isInteger(t.created_at)&&now-t.created_at>=0&&now-t.created_at<=900;
  const pass=b.status==='READY'&&b.errors.length===0&&a?.mode==='OFF'&&a.open_positions===0&&a.pending===false&&a.pending_exit===false&&a.data_recovery_armed===false&&a.risk_code===null&&a.strategy==='SR_BOUNCE'&&a.timeframe==='5m'&&amount(a.balance)!=='Не подтверждено'&&Number(a.balance)>0&&h?.status==='PASS'&&h.source===SOURCE&&h.read_only===true&&h.requires_owner_review===false&&['MATCHED','NOT_ESTABLISHED'].includes(h.anchor_status)&&m?.status==='PASS'&&m.history_complete===true&&m.bars>=1000&&m.last_closed_at===Math.floor(now/300)*300&&s?.status==='PASS'&&ticks.length===2&&ticks.every(validTick)&&now-ticks[0].created_at<=360&&now-ticks[1].created_at<=660&&ticks[0].tick_id!==ticks[1].tick_id&&ticks[0].scheduled_at-ticks[1].scheduled_at===300&&g?.preview_only===true;
  const lines=['Прочитано UTC: '+utc(b.checked_at)];
  if(a){lines.push('Supabase: счёт прочитан · PAPER '+(['OFF','ON','PAUSED','EMERGENCY'].includes(a.mode)?a.mode:'Не подтверждено'),'Баланс: '+amount(a.balance)+' USDT · PnL: '+amount(a.realized_pnl)+' · комиссии: '+amount(a.fees),'Позиции: '+([0,1].includes(a.open_positions)?a.open_positions:'?')+' · pending: '+flag(a.pending)+' · pending_exit: '+flag(a.pending_exit),'Восстановление данных: '+flag(a.data_recovery_armed)+' · риск: '+(a.risk_code===null?'PASS':code(a.risk_code)),
   'Чтение счёта UTC: '+utc(a.last_confirmed_read_at)+' · сохранено UTC: '+utc(a.last_saved_at));}
  if(a?.position)lines.push('Позиция: '+(['LONG','SHORT'].includes(a.position.direction)?a.position.direction:'Не подтверждено')+' · Entry '+amount(a.position.entry_price)+' · размер '+amount(a.position.size)+' · SL '+amount(a.position.stop_loss)+' · TP '+amount(a.position.take_profit));
  if(m){lines.push('Bitget BTCUSDT USDT-M Futures · 5m: '+code(m.status));if(m.status==='PASS')lines.push('Последняя закрытая свеча UTC: '+utc(m.last_closed_at),'Получено UTC: '+utc(m.received_at)+' · возраст: '+Number(m.candle_age_seconds)+' с','Запрос: '+Number(m.request_duration_ms)+' мс · история: '+Number(m.bars)+' свечей');else lines.push(code(m.code));}
  if(h){if(h.comparison==='EXACT_NUMERIC_V1')lines.push('История: точное сравнение чисел без округления · EXACT_NUMERIC_V1');lines.push('История относительно сохранённого якоря: '+code(h.status)+' · '+code(h.anchor_status),'UTC якоря: '+utc(h.anchor_timestamp)+' · проверено: '+utc(h.checked_at));if(h.code)lines.push('Причина истории: '+code(h.code));if(h.change_classification)lines.push('Тип изменения: '+code(h.change_classification));if(Array.isArray(h.changed_fields))lines.push('Поля: '+h.changed_fields.filter(x=>['open','high','low','close','volume'].includes(x)).join(', '));for(const [label,key] of [['Сохранённый хеш','old_ohlcv_hash'],['Текущий хеш','new_ohlcv_hash']])if(typeof h[key]==='string'&&/^[a-f0-9]{64}$/.test(h[key]))lines.push(label+': '+h[key]);if(h.requires_owner_review)lines.push('Автоматическое принятие другой истории запрещено. Нужна проверка владельца; диагностика не меняет якорь.');}
  if(g)lines.push('Текущий сигнал: '+(['LONG','SHORT'].includes(g.direction)?g.direction:'Нет')+' · '+code(g.strategy_reason),'Причина отсутствия входа: '+code(g.entry_blocker),'Последнее сохранённое решение: '+code(g.production_last_decision));
  if(g?.saved_signal)lines.push('Последний сохранённый сигнал: '+(['LONG','SHORT'].includes(g.saved_signal.direction)?g.saved_signal.direction:'Не подтверждено')+' · '+utc(g.saved_signal.signal_at)+' · '+code(g.saved_signal.reason));
  for(const t of ticks.filter(validTick))lines.push('Автоцикл UTC '+utc(t.scheduled_at)+' → сохранён '+utc(t.created_at)+' · '+t.tick_id+' · COMPLETED/OFF');
  lines.push('Источник автоциклов: метаданные авторизованного Worker + квитанции БД. Независимый Cloudflare audit и получение HTTP-ответа Worker не проверены.');
  if(Array.isArray(b.events))for(const e of b.events.slice(0,10))lines.push('Событие '+code(e.kind)+' · '+utc(e.created_at)+' · '+code(e.reason));
  if(b.errors.length)lines.push('Блокировки: '+b.errors.map(code).join('; '));
  if(!pass&&!b.errors.length)lines.push('BLOCKED: неполный или противоречивый ответ.');
  return {status:pass?'READY':'BLOCKED',text:lines.join('\n')};
 }
 if(typeof module!=='undefined')module.exports={view};
 if(typeof document==='undefined')return;
 const button=document.getElementById('a43-pr-check'),status=document.getElementById('a43-pr-status'),details=document.getElementById('a43-pr-details');
 if(!button||!status||!details)return;
 let snapshot=null,busy=false,closed=false,controller=null;
 function render(){const v=view(snapshot);status.textContent=v.status;details.textContent=v.text;}
 button.addEventListener('click',async()=>{
  if(busy||closed)return;busy=true;button.disabled=true;snapshot=null;render();status.textContent='Проверка без изменения PAPER…';
  controller=new AbortController();const timer=setTimeout(()=>controller.abort(),50000);
  try{const r=await fetch('/api/active43/paper-readiness',{method:'GET',credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});if(!r.ok)throw Error('READ_FAILED');const b=await r.json();if(!closed){snapshot=b;render();}}
  catch{snapshot=null;if(!closed)render();}
  finally{clearTimeout(timer);controller=null;busy=false;if(!closed)button.disabled=false;}
 });
 const timer=setInterval(()=>{if(!closed&&!busy)render();},5000);
 window.addEventListener('pagehide',()=>{closed=true;clearInterval(timer);controller?.abort();});render();
})();

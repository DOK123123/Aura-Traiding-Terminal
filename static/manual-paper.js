/* User-confirmed virtual ledger. Analyst events can only populate a draft. */
(function(root){'use strict';
 const KEY='aura-manual-paper-v1-pending';
 const decimal=x=>typeof x==='string'&&/^\d{1,12}(\.\d{1,12})?$/.test(x)&&Number.isFinite(Number(x))&&Number(x)>0;
 function fresh(q,now=Date.now()){return q?.source==='Bitget USDT-M Futures'&&q?.symbol==='BTCUSDT'&&q?.product==='USDT-FUTURES'&&Number.isInteger(q.time)&&now>=q.time&&now-q.time<=5000&&decimal(q.bid)&&decimal(q.ask)&&Number(q.ask)>=Number(q.bid);}
 function model(s,now=Date.now()){
  const ok=s?.mode==='MANUAL_PAPER'&&s?.virtual_only===true&&s?.real_money_execution==='DISABLED';
  const market=ok&&fresh(s.quote,now)&&!s.market_error;
  return {ok,market,canOpen:!!(market&&!s.position),canClose:!!(market&&s.position),pnl:market?s.position_net_pnl:null,equity:market?s.equity:null};
 }
 function signalFresh(v,now=Date.now()/1000){return !!(v?.fresh&&['LONG','SHORT'].includes(v.state)&&v.scenario&&Number.isFinite(v.generated)&&v.generated<=now&&Number.isFinite(v.valid_until)&&v.valid_until>now&&v.valid_until<=v.generated+60);}
 function validIntent(p){
  if(!p||!/^[a-f0-9]{32}$/.test(p.body?.request_id))return false;
  if(/^\/api\/manual-paper\/positions\/[a-f0-9]{32}\/close$/.test(p.path))return Object.keys(p.body).length===1;
  return p.path==='/api/manual-paper/orders'&&['LONG','SHORT'].includes(p.body.side)&&['quantity','stop','target'].every(k=>decimal(p.body[k]))&&
   (p.body.entry_limit===undefined||decimal(p.body.entry_limit))&&(p.body.analyst_at===undefined||Number.isFinite(p.body.analyst_at)&&p.body.analyst_at>0)&&
   Object.keys(p.body).every(k=>['request_id','side','quantity','stop','target','entry_limit','analyst_at'].includes(k));
 }
 function requestId(){const bytes=new Uint8Array(16);root.crypto.getRandomValues(bytes);return Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');}
 if(typeof module!=='undefined')module.exports={fresh,model,signalFresh,validIntent};
 if(!root.document)return;
 const d=root.document,panel=d.getElementById('manual-paper-panel');if(!panel)return;
 const el=k=>d.getElementById('mp-'+k);
 const num=x=>x!==null&&x!==undefined&&Number.isFinite(Number(x))?Number(x).toLocaleString('ru-RU',{maximumFractionDigits:8}):'—';
 const date=x=>typeof x==='number'?new Date(x).toLocaleString('ru-RU'):'—';
 const messages={MANUAL_PAPER_DISABLED:'Ручной счёт выключен в конфигурации сервера',PERSISTENT_STORAGE_NOT_READY:'Постоянное хранилище не подключено',STORAGE_UNAVAILABLE:'Хранилище недоступно. Исход запроса может быть неизвестен — повторите тот же запрос.',WRITE_LIMIT:'Журнал достиг лимита. Новые входы запрещены; закрытие существующей позиции сохраняется.',CORRUPT_JOURNAL:'Ошибка целостности журнала. Баланс не сброшен.',STALE_QUOTE:'Котировка устарела',MARKET_UNAVAILABLE:'Bitget недоступен',RISK_LIMIT:'Риск с комиссиями превышает 0,5% баланса',POSITION_SIZE_LIMIT:'Объём превышает 2000 USDT или баланс',INVALID_STOPS:'Проверьте SL/TP относительно текущей цены',POSITION_ALREADY_OPEN:'Уже есть открытая позиция',POSITION_NOT_FOUND:'Позиция уже закрыта или изменилась',DRAWDOWN_LIMIT:'Новые входы запрещены: просадка 10%',IDEMPOTENCY_CONFLICT:'Ключ запроса уже использован с другими параметрами',INSUFFICIENT_QUOTE_LIQUIDITY:'Недостаточно объёма на лучшей цене Bitget',STALE_ANALYST:'Сценарий истёк или заменён. Обновите ANALYST.',ANALYST_PLAN_CHANGED:'План отличается от сценария. Выберите самостоятельный план.',ENTRY_OUTSIDE_ZONE:'Цена уже вне зоны ANALYST',ENTRY_PRICE_MOVED:'Цена вышла за подтверждаемый предел входа'};
 let state=null,busy=false,reading=false,pending=null,draft=null,signal=null,copied=null,page=0,generation=0,closed=false,storageError=false;
 try{const raw=root.localStorage.getItem(KEY),p=JSON.parse(raw||'null');if(raw&&!validIntent(p))storageError=true;else if(p)pending=p;}catch(_){storageError=true;}
 function copiedValid(){return !copied||(signalFresh(signal)&&signal.generated===copied.generated&&signal.state===copied.state);}
 function dismiss(){draft=null;if(el('confirm-dialog').open)el('confirm-dialog').close();render();}
 function render(){
  const v=model(state),invalid=!copiedValid(),locked=busy||!!pending||!!draft||storageError;
  for(const k of ['balance','realized_pnl'])el(k).textContent=v.ok?num(state[k]):'—';
  el('equity').textContent=num(v.equity);el('pnl').textContent=num(v.pnl);
  el('quote').textContent=v.market?`Bid ${num(state.quote.bid)} / Ask ${num(state.quote.ask)} · ${date(state.quote.time)}`:'Нет свежей подтверждённой котировки';
  el('storage').textContent=v.ok?(state.storage_durable?(state.storage_backend==='SUPABASE_MANUAL_PAPER_V1'?'Supabase · баланс сохранён':'Постоянный диск · баланс сохранён'):'Локальный тестовый счёт · синтетический стенд'):'Чтение баланса не подтверждено';
  const p=v.ok?state.position:null;
  el('position').textContent=v.ok?(p?`${p.side} · ${num(p.quantity)} BTC · вход ${num(p.entry)} · SL ${num(p.stop)} / TP ${num(p.target)} · комиссия входа ${num(p.entry_fee)} USDT`:'Нет открытой позиции'):'—';
  el('protection').textContent=state?.protection_error?`Защитные выходы приостановлены: ${messages[state.protection_error]||'данные недоступны'}`:p?`SL/TP проверяются сервером каждые 5 с. Последняя проверка: ${date(state.protection_checked_at?state.protection_checked_at*1000:null)}`:'SL/TP: нет позиции';
  el('source').textContent=copied?(invalid?'Скопированный сценарий истёк / WAIT. Обновите его или явно выберите самостоятельный план.':`Сценарий ${copied.state} · ${date(copied.generated*1000)} · только план`):'Самостоятельный план · решение принимаете вы';
  el('copy').disabled=locked||!!p||!signalFresh(signal);
  el('manual').disabled=locked||!copied;
  el('use-quote').disabled=locked||!v.canOpen;
  for(const side of ['long','short'])el(side).disabled=locked||!v.canOpen||invalid||!!(copied&&copied.state!==side.toUpperCase());
  el('close').disabled=locked||!v.canClose;
  for(const k of ['entry','quantity','stop','target'])el(k).disabled=locked||!!p;
  el('retry').hidden=!pending;el('retry').disabled=busy;
  el('refresh').disabled=busy||reading;
  el('prev').disabled=busy||page===0;el('next').disabled=busy||!state?.history_has_more;
  el('confirm').disabled=busy||!draft||Date.now()>=draft.expiresAt||
   (draft?.intent.path==='/api/manual-paper/orders'&&!copiedValid());
  if(draft&&Date.now()>=draft.expiresAt)el('confirm-status').textContent='Расчёт устарел. Отмените и проверьте снова.';
  el('history').replaceChildren();
  for(const t of v.ok?state.trades:[]){const row=d.createElement('li');row.textContent=`${date(t.closed_at)} · ${t.side} · ${t.reason} · ${num(t.entry)} → ${num(t.exit)} · ${num(t.quantity)} BTC · Gross ${num(t.gross)} · Net ${num(t.net)} USDT · комиссии ${num(t.fees)}`;el('history').append(row);}
  if(!state?.trades?.length){const row=d.createElement('li');row.textContent=v.ok?'Закрытых сделок на этой странице нет':'История не загружена';el('history').append(row);}
 }
 async function http(path,body){
  const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);
  try{const r=await root.fetch(path,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',redirect:'error',headers:body?{'Content-Type':'application/json','X-Aura-Paper':'local-only'}:{},body:body?JSON.stringify(body):undefined,signal:abort.signal});const data=await r.json();if(!r.ok){const e=new Error(r.status===401?'Войдите как владелец':messages[data.code]||`Операция отклонена (HTTP ${r.status})`);e.status=r.status;throw e;}return data;}finally{clearTimeout(timer);}
 }
 async function refresh(){
  if(busy||reading||closed)return;const gen=++generation;reading=true;
  try{const next=await http('/api/manual-paper/state?offset='+page*50);if(gen!==generation||closed)return;state=next;el('status').textContent=pending?'Есть неподтверждённый запрос. Повторите его тем же ключом.':state.market_error?(messages[state.market_error]||'Источник недоступен'):'Счёт прочитан. Только виртуальные средства.';}
  catch(e){if(gen!==generation||closed)return;state=null;el('status').textContent=e.message;}
  finally{reading=false;render();}
 }
 async function send(intent){
  if(busy||closed||storageError)return;
  if(!root.navigator?.locks){el('status').textContent='Для безопасного повтора нужен браузер с Web Locks и HTTPS.';return;}
  await root.navigator.locks.request('aura-manual-trader-command',{mode:'exclusive',ifAvailable:true},async lock=>{
   if(!lock){el('status').textContent='Другая вкладка выполняет команду. Дождитесь результата.';return;}
   try{
    const raw=root.localStorage.getItem(KEY),saved=JSON.parse(raw||'null');
    if(raw&&!validIntent(saved)){storageError=true;render();el('status').textContent='Повреждён ключ повтора. Новые операции заблокированы.';return;}
    if(intent&&saved){pending=saved;render();el('status').textContent='Есть запрос другой вкладки. Сначала получите его результат.';return;}
    if(!intent){pending=saved;if(!pending){render();return;}}
   }catch(_){storageError=true;render();el('status').textContent='Локальное хранение недоступно. Операция не отправлена.';return;}
   await sendLocked(intent);
  });
 }
 async function sendLocked(intent){
  if(busy||closed)return;
  if(intent){try{root.localStorage.setItem(KEY,JSON.stringify(intent));pending=intent;}catch(_){el('status').textContent='Браузер не сохранил ключ повтора. Разрешите локальное хранение.';return;}}
  if(!pending)return;
  busy=true;generation++;render();let actionError=null;
  try{const receipt=await http(pending.path,pending.body);if(receipt.request_id!==pending.body.request_id)throw new Error('Некорректное подтверждение. Повторите запрос.');root.localStorage.removeItem(KEY);pending=null;page=0;el('status').textContent='Виртуальная операция сохранена.';}
  catch(e){
   // Definite transactional rejections may clear intent; unknown outcomes retain it.
   if([409,422,403].includes(e.status)){try{root.localStorage.removeItem(KEY);pending=null;}catch(_){/* Retain safe replay identity. */}}
   actionError=e.message;el('status').textContent=e.message+(pending?' Повторите неподтверждённый запрос.':'');
  }finally{busy=false;state=null;render();}
  if(!pending)await refresh();
  if(actionError)el('status').textContent=actionError+(pending?' Повторите неподтверждённый запрос.':'');
 }
 async function prepare(side){
  if(!model(state).canOpen||!copiedValid()||pending||busy||draft||closed)return;
  if(copied&&copied.state!==side)return;
  const fields=['entry','quantity','stop','target'];if(fields.some(k=>!el(k).checkValidity()||!decimal(el(k).value))){fields.forEach(k=>el(k).reportValidity());el('status').textContent='Заполните положительные Entry, объём, SL и TP.';return;}
  const body={request_id:requestId(),side,quantity:el('quantity').value,stop:el('stop').value,target:el('target').value,entry_limit:el('entry').value};
  if(copied)body.analyst_at=copied.generated;
  busy=true;generation++;render();
  try{const p=await http('/api/manual-paper/preview',body);
   if(closed)return;
   if(p.read_only!==true||p.mode!=='MANUAL_PAPER'||p.virtual_only!==true||p.real_money_execution!=='DISABLED'||!decimal(p.risk)||!Number.isFinite(p.expires_at)||p.expires_at<=Date.now()||!copiedValid())throw Error('Расчёт устарел или не подтверждён.');
   // Tighten the user's price bound to the displayed execution estimate. A
   // favorable move is allowed; an adverse move requires a new risk review.
   body.entry_limit=p.entry;
   draft={intent:{path:'/api/manual-paper/orders',body},expiresAt:Math.min(p.expires_at,copied?copied.valid_until*1000:Infinity)};
   el('confirm-text').textContent=`Открыть виртуальный ${side}: ${num(p.quantity)} BTC по текущим ${num(p.entry)} USDT. Предел входа ${num(body.entry_limit)}. SL ${num(p.stop)} / TP ${num(p.target)}. Номинал ${num(p.notional)} USDT. Риск до SL с комиссиями ${num(p.risk)} USDT (${num(p.risk_pct)}%, максимум ${num(p.max_risk)}). Комиссия входа ${num(p.entry_fee)}, выхода у SL ${num(p.stop_exit_fee)}. Потенциал Net ${num(p.net_reward)} · R/R ${num(p.net_rr)}. Цена повторно проверяется сервером; гэп может увеличить убыток.`;
   el('risk').textContent=`Проверка сервера: риск ${num(p.risk)} USDT · ${num(p.risk_pct)}% · R/R после комиссий ${num(p.net_rr)}`;
   el('confirm-status').textContent='Только ваше подтверждение отправляет команду виртуальному счёту.';el('confirm-dialog').showModal();
  }catch(e){el('status').textContent=e.message;}finally{busy=false;render();}
 }
 for(const side of ['LONG','SHORT'])el(side.toLowerCase()).addEventListener('click',()=>prepare(side));
 el('close').addEventListener('click',()=>{if(!model(state).canClose||pending||busy||draft||closed)return;
  draft={intent:{path:'/api/manual-paper/positions/'+state.position.id+'/close',body:{request_id:requestId()}},expiresAt:state.quote.time+30000};
  el('confirm-text').textContent=`Закрыть виртуальную ${state.position.side} ${num(state.position.quantity)} BTC? Текущий Net PnL ${num(state.position_net_pnl)} USDT включает обе комиссии. Цена выхода будет заново получена сервером.`;
  el('confirm-status').textContent='Подтвердите закрытие этой позиции.';el('confirm-dialog').showModal();render();
 });
 el('confirm').addEventListener('click',()=>{render();if(el('confirm').disabled)return;const intent=draft.intent;draft=null;el('confirm-dialog').close();send(intent);});
 el('cancel').addEventListener('click',dismiss);el('confirm-dialog').addEventListener('cancel',e=>{e.preventDefault();dismiss();});
 el('copy').addEventListener('click',()=>{if(busy||pending||draft||!signalFresh(signal)||state?.position)return;copied=structuredClone(signal);const p=copied.scenario;el('entry').value=String(p.reference_entry);el('stop').value=String(p.stop_loss);el('target').value=String(p.take_profit);el('risk').textContent='План скопирован. Задайте объём и проверьте риск на сервере.';render();});
 el('manual').addEventListener('click',()=>{if(busy||pending||draft)return;copied=null;el('risk').textContent='Самостоятельный план. Нужна новая проверка риска.';render();});
 el('use-quote').addEventListener('click',()=>{if(!model(state).canOpen||busy||pending||draft)return;el('entry').value=String(state.quote.ask);el('risk').textContent='Предел LONG = ask. Для SHORT задайте минимальную допустимую цену (bid).';});
 for(const k of ['entry','quantity','stop','target'])el(k).addEventListener('input',()=>{el('risk').textContent='Параметры изменены. Нужна новая проверка риска.';});
 el('retry').addEventListener('click',()=>send());el('refresh').addEventListener('click',refresh);
 el('prev').addEventListener('click',()=>{if(!busy&&page>0){page--;refresh();}});el('next').addEventListener('click',()=>{if(!busy&&state?.history_has_more){page++;refresh();}});
 panel.addEventListener('toggle',()=>{if(panel.open)refresh();});
 root.addEventListener('aura-analyst-snapshot',e=>{signal=e.detail;render();});
 root.addEventListener('pagehide',()=>{closed=true;generation++;signal=null;draft=null;if(el('confirm-dialog').open)el('confirm-dialog').close();render();});
 root.addEventListener('pageshow',e=>{if(e.persisted){closed=false;state=null;signal=null;render();if(panel.open)refresh();}});
 d.addEventListener('visibilitychange',()=>{if(d.hidden){signal=null;draft=null;if(el('confirm-dialog').open)el('confirm-dialog').close();render();}else if(panel.open)refresh();});
 root.setInterval(()=>{if(panel.open){render();if(!d.hidden&&!draft)refresh();}},3000);
 root.setInterval(()=>{if(panel.open)render();},250);
 render();if(panel.open)refresh();
})(typeof window==='undefined'?globalThis:window);

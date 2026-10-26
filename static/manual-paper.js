/* Separate virtual account; no automatic entries or Active43 controls. */
(function(){'use strict';
 const KEY='aura-manual-paper-v1-pending';
 function fresh(q,now=Date.now()){return q?.source==='Bitget USDT-M Futures'&&q?.symbol==='BTCUSDT'&&q?.product==='USDT-FUTURES'&&Number.isInteger(q.time)&&now>=q.time&&now-q.time<=5000&&Number(q.bid)>0&&Number(q.ask)>=Number(q.bid);}
 function model(s,now=Date.now()){
  const ok=s?.mode==='MANUAL_PAPER'&&s?.virtual_only===true&&s?.real_money_execution==='DISABLED';
  const market=ok&&fresh(s.quote,now)&&!s.market_error;
  return {ok,market,canOpen:!!(market&&!s.position),canClose:!!(market&&s.position),pnl:market?s.position_net_pnl:null,equity:market?s.equity:null};
 }
 function requestId(){const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);return Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');}
 if(typeof module!=='undefined')module.exports={fresh,model};
 if(typeof document==='undefined')return;
 const panel=document.getElementById('manual-paper-panel');if(!panel)return;
 const el=k=>document.getElementById('mp-'+k);
 const num=x=>x!==null&&x!==undefined&&Number.isFinite(Number(x))?Number(x).toLocaleString('ru-RU',{maximumFractionDigits:8}):'—';
 const date=x=>typeof x==='number'?new Date(x).toLocaleString('ru-RU'):'—';
 const messages={MANUAL_PAPER_DISABLED:'Ручной счёт выключен в конфигурации сервера',PERSISTENT_STORAGE_NOT_READY:'Постоянное хранилище не подключено',STORAGE_UNAVAILABLE:'Хранилище недоступно. Исход запроса может быть неизвестен — повторите тот же запрос.',WRITE_LIMIT:'Журнал достиг лимита. Новые входы запрещены; закрытие существующей позиции сохраняется.',CORRUPT_JOURNAL:'Ошибка целостности журнала. Баланс не сброшен.',STALE_QUOTE:'Котировка устарела',MARKET_UNAVAILABLE:'Bitget недоступен',RISK_LIMIT:'Риск с комиссиями превышает 0,5% баланса',POSITION_SIZE_LIMIT:'Объём превышает 2000 USDT или баланс',INVALID_STOPS:'Проверьте SL/TP относительно текущей цены',POSITION_ALREADY_OPEN:'Уже есть открытая позиция',POSITION_NOT_FOUND:'Позиция уже закрыта или изменилась',DRAWDOWN_LIMIT:'Новые входы запрещены: просадка 10%',IDEMPOTENCY_CONFLICT:'Ключ запроса уже использован с другими параметрами',INSUFFICIENT_QUOTE_LIQUIDITY:'Недостаточно объёма на лучшей цене Bitget'};
 let state=null,busy=false,pending=null,page=0,generation=0;
 try{const p=JSON.parse(localStorage.getItem(KEY)||'null');if(p&&typeof p.path==='string'&&/^\/api\/manual-paper\/(orders|positions\/[a-f0-9]{32}\/close)$/.test(p.path)&&/^[a-f0-9]{32}$/.test(p.body?.request_id))pending=p;}catch(_){/* Invalid local intent is not submitted. */}
 function render(){
  const v=model(state);
  for(const k of ['balance','realized_pnl'])el(k).textContent=v.ok?num(state[k]):'—';
  el('equity').textContent=num(v.equity);el('pnl').textContent=num(v.pnl);
  el('quote').textContent=v.market?`Bid ${num(state.quote.bid)} / Ask ${num(state.quote.ask)} · ${date(state.quote.time)}`:'Нет свежей подтверждённой котировки';
  el('storage').textContent=v.ok?(state.storage_durable?(state.storage_backend==='SUPABASE_MANUAL_PAPER_V1'?'Supabase · баланс сохранён':'Постоянный диск · баланс сохранён'):'Локальный тестовый счёт · не для Render'):'Чтение баланса не подтверждено';
  const p=state?.position;
  el('position').textContent=v.ok?(p?`${p.side} · ${num(p.quantity)} BTC · вход ${num(p.entry)} · SL ${num(p.stop)} / TP ${num(p.target)}`:'Нет открытой позиции'):'—';
  el('protection').textContent=state?.protection_error?`Защитные выходы приостановлены: ${messages[state.protection_error]||state.protection_error}`:p?`SL/TP проверяются сервером каждые 5 с. Последняя проверка: ${date(state.protection_checked_at?state.protection_checked_at*1000:null)}`:'SL/TP: нет позиции';
  for(const side of ['long','short'])el(side).disabled=busy||!!pending||!v.canOpen;
  el('close').disabled=busy||!!pending||!v.canClose;
  for(const k of ['quantity','stop','target'])el(k).disabled=busy||!!pending||!!p;
  el('retry').hidden=!pending;el('retry').disabled=busy;
  el('refresh').disabled=busy;
  el('prev').disabled=busy||page===0;el('next').disabled=busy||!state?.history_has_more;
  el('history').replaceChildren();
  for(const t of v.ok?state.trades:[]){const row=document.createElement('li');row.textContent=`${date(t.closed_at)} · ${t.side} · ${t.reason} · ${num(t.entry)} → ${num(t.exit)} · ${num(t.quantity)} BTC · Net ${num(t.net)} USDT · комиссии ${num(t.fees)}`;el('history').append(row);}
  if(!state?.trades?.length){const row=document.createElement('li');row.textContent=v.ok?'Закрытых сделок на этой странице нет':'История не загружена';el('history').append(row);}
 }
 async function http(path,body){
  const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);
  try{const r=await fetch(path,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':'application/json','X-Aura-Paper':'local-only'}:{},body:body?JSON.stringify(body):undefined,signal:abort.signal});const data=await r.json();if(!r.ok){const e=new Error(r.status===401?'Войдите как владелец':messages[data.code]||data.code||`HTTP ${r.status}`);e.status=r.status;throw e;}return data;}finally{clearTimeout(timer);}
 }
 async function refresh(){
  if(busy)return;const gen=++generation;
  try{const next=await http('/api/manual-paper/state?offset='+page*50);if(gen!==generation)return;state=next;el('status').textContent=pending?'Есть неподтверждённый запрос. Повторите его тем же ключом.':state.market_error?(messages[state.market_error]||state.market_error):'Счёт прочитан. Только виртуальные средства.';}
  catch(e){if(gen!==generation)return;state=null;el('status').textContent=e.message;}
  render();
 }
 async function send(intent){
  if(busy)return;
  // Persist intent BEFORE sending: a network timeout must not create a new order ID.
  if(intent){try{localStorage.setItem(KEY,JSON.stringify(intent));pending=intent;}catch(_){el('status').textContent='Браузер не сохранил ключ повтора. Разрешите локальное хранение.';return;}}
  if(!pending)return;
  busy=true;generation++;render();
  let actionError=null;
  try{const receipt=await http(pending.path,pending.body);if(receipt.request_id!==pending.body.request_id)throw new Error('Некорректное подтверждение. Повторите запрос.');localStorage.removeItem(KEY);pending=null;page=0;el('status').textContent='Виртуальная операция сохранена.';}
  catch(e){
   // 409/422 are definite transactional rejections. 5xx/timeouts remain uncertain.
   if([409,422,403].includes(e.status)){localStorage.removeItem(KEY);pending=null;}
   actionError=e.message;el('status').textContent=e.message+(pending?' Повторите неподтверждённый запрос.':'');
  }finally{busy=false;state=null;render();}
  if(!pending)await refresh();
  if(actionError)el('status').textContent=actionError+(pending?' Повторите неподтверждённый запрос.':'');
 }
 for(const side of ['LONG','SHORT'])el(side.toLowerCase()).addEventListener('click',()=>{
  if(!model(state).canOpen||pending||busy)return;
  const fields=['quantity','stop','target'];if(fields.some(k=>!el(k).checkValidity())){fields.forEach(k=>el(k).reportValidity());return;}
  send({path:'/api/manual-paper/orders',body:{request_id:requestId(),side,quantity:el('quantity').value,stop:el('stop').value,target:el('target').value}});
 });
 el('close').addEventListener('click',()=>{if(model(state).canClose&&!pending&&!busy)send({path:'/api/manual-paper/positions/'+state.position.id+'/close',body:{request_id:requestId()}});});
 el('retry').addEventListener('click',()=>send());el('refresh').addEventListener('click',refresh);
 el('prev').addEventListener('click',()=>{if(!busy&&page>0){page--;refresh();}});el('next').addEventListener('click',()=>{if(!busy&&state?.history_has_more){page++;refresh();}});
 panel.addEventListener('toggle',()=>{if(panel.open)refresh();});
 setInterval(()=>{if(panel.open){render();if(!document.hidden)refresh();}},5000);
 setInterval(()=>{if(panel.open)render();},1000);
 render();
})();

/* Independent owner-only peek panel: never invokes status/load or controls. */
(function(){'use strict';
 const reasons={PAPER_NOT_OFF:'Режим PAPER не OFF',OPEN_POSITION_PRESENT:'Есть открытая позиция',PENDING_OPERATION_PRESENT:'Есть ожидающая операция',DATA_RECOVERY_ARMED:'Требуется восстановление данных',DAILY_LOSS_LIMIT:'Достигнут дневной лимит убытка',DRAWDOWN_LIMIT:'Достигнут лимит просадки',EMERGENCY_STOP:'Аварийная остановка',INSUFFICIENT_BALANCE:'Недостаточно виртуальных средств',SCHEDULER_NOT_CONFIGURED:'Не настроена авторизация scheduler',ACTIVE43_DISABLED:'Модуль выключен на сервере',ACTIVE43_BITGET_DISABLED:'Модуль Bitget выключен',ACTIVE43_NOT_CONFIGURED:'Модуль не настроен',SCHEDULER_ACCOUNT_NOT_INITIALIZED:'Счёт не инициализирован',STORAGE_AUTH:'Supabase: ошибка авторизации',STORAGE_PERMISSION_DENIED:'Supabase: недостаточно прав',STORAGE_SCHEMA_MISSING:'Supabase: схема недоступна',OFF_READINESS_INCOMPLETE_STATE:'Неполное состояние счёта',STORAGE_READ_TIMEOUT:'Supabase: превышено время чтения'};
 const SOURCE='Bitget · USDT-M Futures / api.bitget.com';
 function view(b,now=Date.now()/1000){
  const fallback={status:'BLOCKED',mode:'Не подтверждено',position:'Не подтверждено',pending:'Не подтверждено',exit:'Не подтверждено',count:'Не подтверждено',recovery:'Не подтверждено',risk:'Не подтверждено',at:'—',reason:'Нет подтверждённого чтения Supabase'};
  if(!b||b.scope!=='AURA43_ACTIVE_PAPER'||b.market_source!==SOURCE||b.strategy_version!=='AURA_4.3_ACTIVE_PAPER_3'||b.read_only!==true||b.state_changed!==false||b.paper_only!==true||b.exchange_execution!==false||b.purpose!=='OFF_ONLY_ACCOUNT_PRECONDITIONS')return fallback;
  if(b.read_confirmed!==true)return {...fallback,reason:Array.isArray(b.errors)?b.errors.map(x=>reasons[x]||'Состояние Supabase не подтверждено').join('; '):'Supabase: чтение не подтверждено'};
  if(!['OFF','ON','PAUSED','EMERGENCY'].includes(b.mode)||![0,1].includes(b.open_positions)||!['pending','pending_exit','data_recovery_armed','scheduler_auth_configured'].every(k=>typeof b[k]==='boolean')||b.pending_operations!==Number(b.pending)+Number(b.pending_exit)||!Number.isInteger(b.last_confirmed_read_at)||b.last_confirmed_read_at<=0||!b.risk_guards||!['PASS','BLOCKED'].includes(b.risk_guards.status)||!Array.isArray(b.errors)||!b.errors.every(x=>typeof x==='string')||!['PASS','BLOCKED'].includes(b.status))return fallback;
  const age=now-b.last_confirmed_read_at,fresh=age>=-3&&age<=60;
  const pass=fresh&&b.status==='PASS'&&b.mode==='OFF'&&b.open_positions===0&&!b.pending&&!b.pending_exit&&!b.data_recovery_armed&&b.risk_guards.status==='PASS'&&b.risk_guards.code===null&&b.scheduler_auth_configured&&b.errors.length===0;
  return {status:pass?'PASS':'BLOCKED',mode:b.mode,position:b.open_positions?'Да · 1':'Нет · 0',pending:b.pending?'Есть':'Нет',exit:b.pending_exit?'Есть':'Нет',count:String(b.pending_operations),recovery:b.data_recovery_armed?'true':'false',risk:b.risk_guards.status==='PASS'?'PASS':'BLOCKED · '+(reasons[b.risk_guards.code]||'Проверка риска не пройдена'),at:new Date(b.last_confirmed_read_at*1000).toISOString(),reason:!fresh?'Снимок устарел — повторите проверку':pass?'Пустой OFF-счёт допускает off_only. Торговля и Cloudflare не включены.':b.errors.map(x=>reasons[x]||'Серверная проверка не пройдена').join('; ')||'Запуск off_only заблокирован: состояние не подтверждено'};
 }
 if(typeof module!=='undefined')module.exports={view};
 if(typeof document==='undefined')return;
 const panel=document.getElementById('active43-off-readiness');if(!panel)return;
 const out=k=>document.getElementById('a43-ro-'+k);let snapshot=null,busy=false,closed=false,controller=null;
 function render(){const v=view(snapshot);for(const k of ['status','mode','position','pending','exit','count','recovery','risk','at','reason'])out(k).textContent=v[k];}
 out('check').addEventListener('click',async()=>{
  if(busy||closed)return;busy=true;snapshot=null;render();out('check').disabled=true;out('reason').textContent='Чтение Supabase без изменения счёта…';
  controller=new AbortController();const timer=setTimeout(()=>controller.abort(),18000);
  try{
   const response=await fetch('/api/active43/off-only-readiness',{method:'GET',credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
   if(!response.ok)throw Error('READ_FAILED');
   const body=await response.json();if(!closed){snapshot=body;render();}
  }catch{snapshot=null;if(!closed){render();out('reason').textContent='BLOCKED: нет авторизации, ответа БД или подтверждённого состояния. Войдите владельцем и повторите чтение.';}}
  finally{clearTimeout(timer);controller=null;busy=false;if(!closed)out('check').disabled=false;}
 });
 const expiry=setInterval(()=>{if(!busy&&!closed)render();},5000);
 window.addEventListener('pagehide',()=>{closed=true;clearInterval(expiry);controller?.abort();});
 render();
})();

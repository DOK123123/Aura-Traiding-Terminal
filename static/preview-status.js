/* Owner-only GET diagnostics, loaded by the isolated preview page only. */
(function(){'use strict';if(typeof document==='undefined'||document.body?.dataset?.manualPreview!=='true')return;
 const button=document.getElementById('preview-check'),result=document.getElementById('preview-check-result');if(!button||!result)return;
 button.addEventListener('click',async()=>{if(button.disabled)return;button.disabled=true;const c=new AbortController(),timer=setTimeout(()=>c.abort(),24000);
  try{const r=await fetch('/api/preview/readiness',{method:'GET',credentials:'same-origin',cache:'no-store',redirect:'error',signal:c.signal});if(!r.ok)throw Error();const b=await r.json();if(typeof b.ready!=='boolean'||typeof b.manual_enabled!=='boolean'||typeof b.manual_operations_ready!=='boolean'||!['ACTIVE','OFF'].includes(b.protection_worker)||b.scope!=='ISOLATED_MANUAL_PREVIEW'||b.state_changed!==false||b.exchange_execution!==false)throw Error();if(b.ready&&!(b.bitget==='CONNECTED'&&b.supabase==='ISOLATED_SCOPE_CONFIRMED')||b.manual_operations_ready&&!(b.ready&&b.manual_enabled&&b.protection_worker==='ACTIVE'))throw Error();result.textContent=(b.ready===true?'INFRASTRUCTURE PASS':'BLOCKED')+' · Bitget: '+(b.bitget==='CONNECTED'?'CONNECTED':'ERROR')+' · изоляция БД: '+(b.supabase==='ISOLATED_SCOPE_CONFIRMED'?'CONFIRMED':'NOT VERIFIED')+' · Manual Paper: '+(b.manual_enabled?'разрешён вручную':'OFF')+' · защитный worker: '+(b.protection_worker==='ACTIVE'?'ACTIVE':'OFF')+' · ручные операции: '+(b.manual_operations_ready?'READY':'BLOCKED')+'. Диагностика не изменяла счёт.';}
  catch{result.textContent='BLOCKED · нет авторизации, соединения или подтверждённого контракта preview. Счёт не изменён.';}
  finally{clearTimeout(timer);button.disabled=false;}
 });
})();

/* Offline evidence, never a test-trade button or live account mutation. */
(()=>{'use strict';
 const allowed=new Set(['PASS','FAIL','NOT_TESTED','INCONCLUSIVE']);
 function model(data){
  if(data?.read_only!==true||data.live_execution_enabled!==false)return [];
  return [['isolated','Изолированный execution test · TEST ONLY'],['historical','Исторический replay стратегии'],['live','Проверка автономного цикла на Render']].map(([key,title])=>({key,title,status:key==='live'?'NOT_TESTED':allowed.has(data[key]?.status)?data[key].status:'NOT_TESTED',details:data[key]||{}}));
 }
 if(typeof module!=='undefined')module.exports={model};
 if(typeof document==='undefined')return;
 const panel=document.getElementById('execution-verification');if(!panel)return;
 const result=document.getElementById('ev-results'),state=document.getElementById('ev-status'),button=document.getElementById('ev-refresh');let busy=false;
 async function refresh(){
  if(busy)return;busy=true;button.disabled=true;const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);state.textContent='Загрузка сохранённых доказательств…';
  try{
   const r=await fetch('/api/auto42-verification',{credentials:'same-origin',cache:'no-store',signal:abort.signal});
   if(r.status===401||r.status===403){button.hidden=true;result.replaceChildren();state.textContent='Войдите владельцем через ссылку aura.';return;}
   if(!r.ok)throw Error('Unavailable');const data=await r.json();button.hidden=false;result.replaceChildren();
   for(const row of model(data)){
    const section=document.createElement('section'),title=document.createElement('h3'),status=document.createElement('p'),detail=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');
    title.textContent=row.title;status.textContent=row.status;summary.textContent='Доказательства и ограничения';pre.textContent=JSON.stringify(row.details,null,2);detail.append(summary,pre);section.append(title,status,detail);result.append(section);
   }
   state.textContent=data.code_matches===false?'Код изменился после проверки: прежний PASS недействителен.':'Тесты выполнены офлайн. TEST ONLY не является сделкой владельца. Live open/close не подтверждён.';
  }catch{state.textContent='Доказательства недоступны. Успех не подтверждён.';result.replaceChildren();}
  finally{clearTimeout(timer);button.disabled=false;busy=false;}
 }
 panel.addEventListener('toggle',()=>{if(panel.open)refresh();});button.addEventListener('click',refresh);
})();

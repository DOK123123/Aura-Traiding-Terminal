/* Saved production evidence only. No market fetch, strategy calculation or writes. */
(()=>{'use strict';
 function model(data){
  if(data?.read_only!==true||data.exchange_execution!==false)return null;
  const s=data.snapshot;
  if(data.status!=='CAPTURED'||s?.schema!=='AUTO42_ALIGNMENT_1')return {missing:true};
  return {missing:false,...data,rows:['15m','1h','4h'].map(tf=>({tf,...s.frames?.[tf]}))};
 }
 if(typeof module!=='undefined')module.exports={model};
 if(typeof document==='undefined')return;
 const panel=document.getElementById('timeframe-alignment');if(!panel)return;
 const output=document.getElementById('ta-results'),status=document.getElementById('ta-status'),button=document.getElementById('ta-refresh');let busy=false;
 const text=v=>v==null?'Нет данных':String(v);
 const utc=v=>typeof v==='number'?new Date(v*1000).toISOString().replace('T',' ').replace('.000Z',' UTC'):'Нет данных';
 const direction=v=>v===1?'UP (+1)':v===-1?'DOWN (-1)':v===0?'FLAT (0)':'UNKNOWN';
 function line(parent,label,value){const p=document.createElement('p');p.textContent=label+': '+text(value);parent.append(p);}
 async function refresh(){
  if(busy)return;busy=true;button.disabled=true;
  const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);
  status.textContent='Чтение сохранённого production-решения…';
  try{
   const r=await fetch('/api/auto42/alignment',{credentials:'same-origin',cache:'no-store',signal:abort.signal});
   output.replaceChildren();
   if(r.status===401||r.status===403){button.hidden=true;status.textContent='Данные доступны только владельцу. Войдите через ссылку aura.';return;}
   if(!r.ok)throw Error('Unavailable');
   button.hidden=false;const data=model(await r.json());if(!data)throw Error('Invalid evidence');
   if(data.missing){status.textContent='Снимок ещё не записан. Старое сообщение об отказе не позволяет проверить его причину. Ожидайте обычного scheduler tick; панель его не запускает.';return;}
   const s=data.snapshot;
   status.textContent='Сохранённая оценка: '+utc(s.evaluated_at)+' · '+text(s.verdict);
   line(output,'Последняя обработанная 15m (close)',utc(data.last_processed_closed_at));
   line(output,'Последнее решение портфеля / ошибка',text(data.portfolio_last_decision)+' / '+text(data.portfolio_last_error));
   line(output,'Точное решение стратегии',s.strategy_reason);
   line(output,'Причина alignment',s.detail);
   line(output,'Требуется',s.required_condition);
   line(output,'Фактически','mask='+s.known_mask+'; production alignment='+s.alignment_flag+'; условие по сохранённым направлениям='+s.actual_condition);
   line(output,'Корректность alignment',s.decision_valid===true?'Подтверждена согласованность сохранённых входов':s.decision_valid===false?'Обнаружено противоречие во входах':'Не подтверждена');
   line(output,'Свежесть при оценке / сейчас',text(s.freshness?.fresh_at_evaluation)+' / '+text(data.current_data_fresh));
   line(output,'Возраст снимка, секунд',data.age_seconds);
   line(output,'Совпадение с текущим кодом',data.current_code_matches);
   for(const row of data.rows){
    const card=document.createElement('section'),title=document.createElement('h3');title.textContent=row.tf+' · '+direction(row.direction);card.append(title);
    line(card,'Open UTC',utc(row.open_at));line(card,'Close UTC',utc(row.closed_at));line(card,'Требуемый close UTC',utc(row.expected_closed_at));
    for(const key of ['ema20','ema50','adx14','atr14','rsi14','sample_count'])line(card,key,row.indicators?.[key]);
    output.append(card);
   }
   line(output,'Проблемы входов',(s.issues||[]).join(', ')||'Не обнаружены');
   const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');
   summary.textContent='Снимок и идентификаторы кода';pre.textContent=JSON.stringify(s,null,2);details.append(summary,pre);output.append(details);
  }catch{output.replaceChildren();status.textContent='Диагностика недоступна; корректность решения не подтверждена.';}
  finally{clearTimeout(timer);button.disabled=false;busy=false;}
 }
 panel.addEventListener('toggle',()=>{if(panel.open)refresh();});button.addEventListener('click',refresh);
})();

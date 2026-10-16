/* Owner-only saved evidence. No execution actions and no tests run in the UI. */
(()=>{'use strict';
 const states=new Set(['VERIFIED','WAITING_FOR_REAL_SIGNAL','FAILED']);
 function model(data){
  if(data?.read_only!==true||data.paper_only!==true||data.exchange_execution!==false)return null;
  // A status word or offline PASS alone is never accepted as live proof.
  if(data.status==='VERIFIED'&&(!data.live_cycle_verified||!data.verified_cycle?.open?.signal||!data.verified_cycle?.close))return {...data,status:'FAILED',reason:'INCOMPLETE_LIVE_EVIDENCE'};
  return {...data,status:states.has(data.status)?data.status:'FAILED'};
 }
 if(typeof module!=='undefined')module.exports={model};
 if(typeof document==='undefined')return;
 const panel=document.getElementById('live-paper-monitor');if(!panel)return;
 const output=document.getElementById('lpm-results'),state=document.getElementById('lpm-status'),button=document.getElementById('lpm-refresh');let busy=false,timer;
 const text=x=>x==null?'Нет данных':String(x);
 const utc=x=>typeof x==='number'?new Date(x*1000).toISOString().replace('T',' ').replace('.000Z',' UTC'):'Нет данных';
 function line(parent,label,value){const p=document.createElement('p');p.textContent=label+': '+text(value);parent.append(p);}
 function details(label,data){const d=document.createElement('details'),s=document.createElement('summary'),pre=document.createElement('pre');s.textContent=label;pre.textContent=JSON.stringify(data,null,2);d.append(s,pre);output.append(d);}
 async function refresh(){
  if(busy)return;busy=true;button.disabled=true;
  const abort=new AbortController(),deadline=setTimeout(()=>abort.abort(),15000);
  try{
   const response=await fetch('/api/auto42/live-monitor',{credentials:'same-origin',cache:'no-store',signal:abort.signal});
   output.replaceChildren();
   if(response.status===401||response.status===403){button.hidden=true;state.textContent='Вход владельца необходим. Live verification не подтверждена.';return;}
   const data=model(await response.json());if(!data)throw Error('Invalid evidence');button.hidden=false;
   state.textContent=data.status+' · '+text(data.reason);
   line(output,'Auto Paper',data.mode);line(output,'Последний scheduler tick',utc(data.last_scheduler_tick));
   line(output,'Последний обработанный 15m close',utc(data.last_processed_closed_at));
   line(output,'Последний сигнал',data.last_signal?utc(data.last_signal.utc_timestamp)+' · '+text(data.last_signal.details?.direction)+' · '+text(data.last_signal.scheduler_run_id):'Сохранённый сигнал пока отсутствует');
   line(output,'Последний отказ во входе',data.entry_rejection?utc(data.entry_rejection.utc_timestamp)+' · '+text(data.entry_rejection.reason):data.last_decision);
   line(output,'Текущая ошибка',data.last_error);
   const p=data.position;
   line(output,'Открытая виртуальная позиция',p?text(p.id)+' · '+text(p.direction):'Нет');
   if(p){line(output,'Время открытия',utc(p.entry_time));line(output,'Entry / SL / TP',text(p.entry_price)+' / '+text(p.stop_loss)+' / '+text(p.take_profit));line(output,'Net PnL позиции с entry/exit комиссиями',p.net_pnl_including_entry_fee);line(output,'Время оценки PnL',utc(p.marked_at));line(output,'Оценка свежая',data.position_mark_fresh);if(!data.position_mark_fresh)line(output,'Последний известный PnL',p.last_known_net_pnl);}
   const close=data.last_close;
   line(output,'Последнее закрытие',close?utc(close.details?.exit_time)+' · '+text(close.position_id):'Не зафиксировано');
   if(close){line(output,'Причина закрытия',close.reason);line(output,'Комиссии сделки',close.details?.fees);line(output,'Итоговый PnL сделки',close.details?.realized_pnl);}
   line(output,'Баланс / свежая equity',text(data.balance)+' / '+text(data.equity));line(output,'Накопленный realized PnL / комиссии',text(data.realized_pnl)+' / '+text(data.fees));
   const storage=data.storage||{};line(output,'Хранилище / durable',text(storage.backend)+' / '+text(storage.durable));line(output,'Состояние прочитано и checksum проверен',storage.state_read_verified);line(output,'Сохранено UTC / revision',utc(storage.last_saved_at)+' / '+text(storage.revision));
   line(output,'Изолированный технический тест',text(data.technical_test?.status)+' · TEST ONLY; не доказательство live');
   line(output,'Журнал','Последнее ограниченное окно. Полная постраничная история: owner API /api/auto42/live-monitor/events');
   for(const e of (data.events||[]).slice(0,60)){const row=document.createElement('p');row.textContent=utc(e.utc_timestamp)+' · '+text(e.event_type)+' · '+text(e.position_id)+' · '+text(e.reason)+' · run '+text(e.scheduler_run_id)+' · '+text(e.candle_id)+' · '+text(e.source);output.append(row);}
   details('Сохранённое доказательство OPEN → CLOSE',data.verified_cycle||{status:'WAITING_FOR_REAL_SIGNAL'});details('Изолированная проверка',data.technical_test||{status:'NOT_TESTED'});
  }catch{output.replaceChildren();state.textContent='FAILED · монитор недоступен; автономный цикл не подтверждён.';}
  finally{clearTimeout(deadline);button.disabled=false;busy=false;}
 }
 function schedule(){clearInterval(timer);if(panel.open&&!document.hidden){refresh();timer=setInterval(refresh,30000);}}
 panel.addEventListener('toggle',schedule);document.addEventListener('visibilitychange',schedule);button.addEventListener('click',refresh);
})();

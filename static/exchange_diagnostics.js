/* Manual owner-only public connectivity test. Never a trading data source. */
(()=>{'use strict';
 const statuses=new Set(['AVAILABLE','PARTIALLY_AVAILABLE','BLOCKED_403','BLOCKED_451','TIMEOUT','RATE_LIMITED','INVALID_RESPONSE','UNAVAILABLE','NOT_TESTED']);
 const safe=s=>statuses.has(s)?s:'NOT_TESTED';
 const price=x=>typeof x==='string'&&Number.isFinite(Number(x))&&Number(x)>0?x:'—';
 function rows(data){
  if(data?.read_only!==true||data?.trading_enabled!==false)return [];
  return ['BINGX','BITGET','BYBIT'].map(name=>{
   const d=data.exchanges?.[name]||{},r=d.rest||d,w=d.websocket||{},at=d.tested_at_ms;
   return {name,rest:safe(r.status),ws:safe(w.status),last:price(r.last_price||w.last_price),mark:price(r.mark_price||w.mark_price),freshness:r.mark_freshness?'Last '+(r.freshness||'UNVERIFIED')+' / Mark '+r.mark_freshness:r.freshness||w.freshness||(w.status==='AVAILABLE'?'Проверена при чтении preview':'Не подтверждена'),time:Number.isFinite(at)?new Date(at).toISOString():'Не проверено',detail:JSON.stringify(d,null,2)};
  });
 }
 if(typeof module!=='undefined')module.exports={rows,safe,price};
 if(typeof document==='undefined')return;
 const panel=document.getElementById('exchange-diagnostics');if(!panel)return;
 const button=document.getElementById('ed-run'),message=document.getElementById('ed-status'),list=document.getElementById('ed-results');let busy=false,controller;
 function render(data){
  list.replaceChildren();
  for(const row of rows(data)){
   const section=document.createElement('section'),title=document.createElement('h3');title.textContent=row.name+' Futures';section.append(title);
   for(const [label,value] of [['REST',row.rest],['WebSocket',row.ws],['Last Price',row.last],['Mark Price',row.mark],['Свежесть на момент теста',row.freshness],['Тест, UTC',row.time]]){
    const p=document.createElement('p');p.textContent=label+': '+value;section.append(p);
   }
   const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent='Свечи, задержки и детали';pre.textContent=row.detail;details.append(summary,pre);section.append(details);list.append(section);
  }
 }
 async function request(run){
  if(busy)return;busy=true;button.disabled=true;controller=new AbortController();const timer=setTimeout(()=>controller.abort(),65000);
  message.textContent=run?'Проверка публичных API на сервере · до 60 секунд…':'Загрузка последнего отчёта…';
  try{
   const response=await fetch('/api/exchange-diagnostics'+(run?'/run':''),{method:run?'POST':'GET',credentials:'same-origin',cache:'no-store',headers:run?{'X-Aura-Paper':'local-only'}:{},signal:controller.signal});
   if(response.status===401||response.status===403){button.hidden=true;list.replaceChildren();message.textContent='Требуется вход владельца (aura).';return;}
   const data=await response.json();render(data);
   button.hidden=data.code==='FEATURE_DISABLED';
   message.textContent=data.code==='FEATURE_DISABLED'?'Отключено: AURA_EXCHANGE_DIAGNOSTICS=true требуется на сервере.':!response.ok?'Проверка не запущена: '+(data.code||'ERROR'):'Отчёт сервера. Это разовый тест, а не мониторинг и не разрешение торговли. Цены не являются текущими после завершения теста.';
  }catch{message.textContent='Ошибка или тайм-аут запроса. Результат не подтверждён; повторите после 120 секунд.';}
  finally{clearTimeout(timer);busy=false;button.disabled=false;controller=null;}
 }
 panel.addEventListener('toggle',()=>{if(panel.open)request(false);});button.addEventListener('click',()=>request(true));window.addEventListener('pagehide',()=>controller?.abort());
})();

/* Isolated read-only preview: never changes the main Binance chart or portfolio. */
(()=>{'use strict';
 const expected={exchange:'BYBIT',market_type:'USDT_PERPETUAL',category:'linear',symbol:'BTCUSDT',settlement:'USDT'};
 const validIdentity=d=>d&&Object.entries(expected).every(([k,v])=>d[k]===v);
 function model(d,now=Date.now()/1000){
  const age=now-d?.server_at_ms/1000;
  const valid=d?.read_only===true&&d?.execution_enabled===false&&validIdentity(d.identity)&&d.status==='LIVE'&&age>=0&&age<=10&&['last_price','mark_price'].every(k=>typeof d[k]==='string'&&Number.isFinite(Number(d[k]))&&Number(d[k])>0);
  return {status:valid?'LIVE':(d?.status==='STALE'||d?.status==='LIVE'&&(!Number.isFinite(age)||age<0||age>10))?'STALE — не текущая цена':d?.code==='FEATURE_DISABLED'?'Выключено настройкой сервера':d?.error==='REGION_OR_ACCESS_RESTRICTED'?'Доступ к Bybit запрещён (HTTP 403/451)':'DISCONNECTED — свежие данные недоступны',last:valid?d.last_price:'—',mark:valid?d.mark_price:'—',time:valid?new Date(d.server_at_ms).toISOString():'—',transport:valid?d.transport:'—'};
 }
 if(typeof module!=='undefined')module.exports={model,validIdentity};
 if(typeof document==='undefined')return;
 const panel=document.getElementById('bybit-linear-preview');if(!panel)return;
 let busy=false,closed=false,controller=null,lastData=null;const out=k=>document.getElementById('bl-'+k);
 function render(data){lastData=data;for(const [k,v] of Object.entries(model(data)))out(k).textContent=v;}
 async function refresh(){
  if(busy||closed||!panel.open||document.hidden)return;busy=true;controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);
  try{const r=await fetch('/api/bybit-linear/ticker',{credentials:'same-origin',cache:'no-store',signal:controller.signal});if(r.status===401||r.status===403){render(null);return;}const d=await r.json();if(!closed)render(d);}
  catch{if(!closed)render(null);}
  finally{clearTimeout(timer);controller=null;busy=false;}
 }
 panel.addEventListener('toggle',refresh);out('refresh').addEventListener('click',refresh);
 const timer=setInterval(()=>{if(panel.open&&!document.hidden){render(lastData);refresh();}},2000);
 document.addEventListener('visibilitychange',()=>{render(null);if(!document.hidden)refresh();});
 window.addEventListener('pagehide',()=>{closed=true;clearInterval(timer);controller?.abort();});render(null);
})();

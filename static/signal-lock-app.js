/* Foreground view only. Detection, storage and push are server-owned. */
(function(){'use strict';
const host=document.getElementById('aura-signal-lock');if(!host||!window.AuraSignalLock)return;
const view=AuraSignalLock.mount(host);let live=[],archive=[],pendingId=new URL(location.href).searchParams.get('signal_event');
const historyPane=document.getElementById('app-more');
if(historyPane)historyPane.prepend(view.historyRoot);
const historyMessage=document.createElement('p'),more=document.createElement('button');
historyMessage.setAttribute('role','status');more.type='button';more.textContent='Загрузить более ранние события';
view.historyRoot.append(more,historyMessage);let cursor=1e11,cursorId='f'.repeat(64),cursorFrame='',busy=false;
function update(){
 const ids=new Set(live.map(e=>e.id));view.update([...live,...archive.filter(e=>!ids.has(e.id))]);
 if(pendingId&&view.choose(pendingId)){pendingId=null;document.getElementById('app-tab-signals')?.click();}
}
host.addEventListener('aura-lock-selected',()=>document.getElementById('app-tab-signals')?.click());
window.addEventListener('aura-preview-snapshot',event=>{
 const lock=event.detail?.signal_lock;
 if(Array.isArray(lock?.events)){
  live=lock.events.map(e=>lock.ready?e:{...e,status:['EXPIRED','INVALIDATED'].includes(e.status)?e.status:'UNKNOWN',plan:null});
 }else live=live.map(e=>({...e,status:['EXPIRED','INVALIDATED'].includes(e.status)?e.status:'UNKNOWN',plan:null}));
 const q=lock?.quote,now=Date.now()/1000;
 const fresh=q?.source==='BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2'&&[q.last,q.time,q.received_at].every(Number.isFinite)&&
  now>=q.time&&now-q.time<=5&&now>=q.received_at&&now-q.received_at<=5;
 view.quote(fresh?q.last.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})+' · LIVE':'— · STALE');
 update();
});
more.onclick=async()=>{
 if(busy)return;busy=true;more.disabled=true;
 try{
  if(cursorFrame!==view.frame()){cursor=1e11;cursorId='f'.repeat(64);cursorFrame=view.frame();}
  const params=new URLSearchParams({before:String(cursor),before_id:cursorId,frame:view.frame(),limit:'50'});
  const response=await fetch('/api/preview/lock/history?'+params,{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw Error();const data=await response.json();
  if(!Array.isArray(data.events))throw Error();
  archive.push(...data.events.map(e=>({...e,archived:true,plan:null})));
  if(data.next_before!==null){cursor=data.next_before;cursorId=data.next_before_id;}
  more.hidden=data.events.length<50;historyMessage.textContent=data.events.length?'Загружены архивные снимки. Они не разрешают вход.':'Более ранних событий нет.';update();
 }catch{historyMessage.textContent='История временно недоступна. Повторите загрузку.';}
 finally{busy=false;more.disabled=false;}
};
if(pendingId&&/^[a-f0-9]{64}$/.test(pendingId)){
 fetch('/api/preview/lock/event/'+pendingId,{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(10000)})
  .then(r=>{if(!r.ok)throw Error();return r.json();}).then(row=>{archive.push({...row,archived:true,plan:null});update();})
  .catch(()=>{historyMessage.textContent='Событие пока недоступно. Оно не считается действующим сигналом.';});
}
let timer=null;
function resume(){clearInterval(timer);if(!document.hidden)timer=setInterval(()=>view.tick(),1000);else{live=live.map(e=>({...e,status:['EXPIRED','INVALIDATED'].includes(e.status)?e.status:'UNKNOWN',plan:null}));update();}}
document.addEventListener('visibilitychange',resume);window.addEventListener('pagehide',()=>clearInterval(timer));window.addEventListener('pageshow',resume);resume();
})();

/* No fetch handler, auth cache, subscription secrets, trading calls or remote URLs. */
'use strict';
self.addEventListener('push',event=>{event.waitUntil((async()=>{let value;try{value=event.data.json();}catch{return;}
 if(!value||typeof value.title!=='string'||typeof value.body!=='string'||! /^[a-f0-9]{64}$/.test(value.event_id||''))return;
 const id=/^[a-f0-9]{64}$/.test(value.scenario_id||'')?value.scenario_id:null;
 await self.registration.showNotification(value.title.slice(0,100),{body:value.body.slice(0,240),tag:value.event_id,renotify:false,silent:false,data:{scenario_id:id},timestamp:Date.now()});
})());});
self.addEventListener('notificationclick',event=>{event.notification.close();event.waitUntil((async()=>{
 const id=event.notification.data?.scenario_id;
 const url=new URL('/',self.location.origin);if(/^[a-f0-9]{64}$/.test(id||''))url.searchParams.set('scenario',id);url.hash='app-signals';
 const tabs=await self.clients.matchAll({type:'window',includeUncontrolled:true});
 const tab=tabs.find(c=>new URL(c.url).origin===url.origin);if(tab){await tab.navigate(url.href);await tab.focus();}else await self.clients.openWindow(url.href);
})());});
self.addEventListener('pushsubscriptionchange',event=>{event.waitUntil(self.registration.showNotification('Aura 5 · подписка требует обновления',{body:'Откройте Aura и заново включите Push. Фоновая подписка не восстановлена автоматически.',tag:'aura5-subscription-expired',data:{scenario_id:null}}));});

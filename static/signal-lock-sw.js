/* Public code only. No credentials, subscriber data, prices or private caches. */
'use strict';
self.addEventListener('push', event=>{
  event.waitUntil((async()=>{
    let p;try{p=event.data.json();}catch{return;}
    if(!p||!['CANDIDATE','WATCH','TEST'].includes(p.status)||
       !/^[a-f0-9]{64}$/.test(p.event_id)||!['LONG','SHORT'].includes(p.direction)||
       !['5m','15m','1h','4h'].includes(p.frame)||!Number.isFinite(p.at)||
       !Number.isFinite(p.expires_at)||p.at<0||p.at>1e11||p.expires_at<p.at||
       !Number.isInteger(p.score)||p.score<0||p.score>100)return;
    const stale=Date.now()/1000>p.expires_at;
    await self.registration.showNotification(p.status==='TEST'?'Aura · тест Web Push':'Aura · '+p.direction+' · '+p.frame,{
      body:(stale?'НЕАКТУАЛЕН':p.status)+' · технический балл '+p.score+'/100 · '+
        new Date(p.at*1000).toISOString()+' · снимок обнаружения, проверьте актуальность в Aura · не вероятность прибыли',
      tag:'aura-signal-'+p.event_id+'-'+p.status,renotify:false,
      data:{event_id:p.event_id,test:p.status==='TEST'},timestamp:p.at*1000
    });
  })());
});
self.addEventListener('notificationclick', event=>{
  event.notification.close();
  const id=event.notification.data?.event_id;
  if(!/^[a-f0-9]{64}$/.test(id||''))return;
  // Never use a URL supplied in a push payload.
  const url=new URL(event.notification.data?.test?'/?push_test=1#app-signals':'/?signal_event='+id+'#app-signals',self.location.origin).href;
  event.waitUntil(self.clients.openWindow(url));
});

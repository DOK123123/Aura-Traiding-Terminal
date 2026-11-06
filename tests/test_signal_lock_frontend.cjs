'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {Selection,visible}=require('../static/signal-lock.js');
const id='a'.repeat(64);
test('500 quote updates and new events preserve the reading selection',()=>{
 const view=new Selection();
 for(let i=0;i<500;i++)view.update([{id:'new-'+i},{id}]);
 assert.equal(view.selected,'new-0');
 view.choose(id);view.update([{id:'another'},{id}]);assert.equal(view.selected,id);
});
test('stale, future and expired WATCH cannot expose live levels',()=>{
 const row={id,status:'WATCH',direction:'LONG',valid_until:200,last_seen:100,plan:{entry:100,sl:95,tp:115,net_rr:2,risk_usdt_per_btc:6}};
 assert.equal(visible(row,101).plan.entry,100);
 for(const now of [99,106,NaN]){assert.equal(visible(row,now).status,'UNKNOWN');assert.equal(visible(row,now).plan,null);}
 assert.equal(visible(row,200).status,'EXPIRED');assert.equal(row.status,'WATCH');
 assert.equal(visible({...row,plan:{entry:100}},101).status,'UNKNOWN');
 assert.equal(visible({...row,archived:true},101).plan,null);
});
function worker(){
 const listeners={},notifications=[],opened=[];
 const self={location:{origin:'https://preview.example.invalid'},addEventListener:(k,f)=>listeners[k]=f,
  registration:{showNotification:async(...args)=>notifications.push(args)},clients:{openWindow:async url=>opened.push(url)}};
 vm.runInNewContext(fs.readFileSync('static/signal-lock-sw.js','utf8'),{self,URL,Date});
 return {listeners,notifications,opened};
}
test('service worker validates payload and click stays on own origin (synthetic, not Android delivery)',async()=>{
 const w=worker();let pending;
 const data={event_id:id,status:'WATCH',direction:'LONG',frame:'15m',score:100,at:Date.now()/1000-10,expires_at:Date.now()/1000-1,url:'https://evil.invalid/'};
 w.listeners.push({data:{json:()=>data},waitUntil:p=>pending=p});await pending;
 assert.equal(w.notifications.length,1);assert.match(w.notifications[0][1].body,/НЕАКТУАЛЕН/);
 assert.equal(w.notifications[0][1].renotify,false);
 w.listeners.notificationclick({notification:{close(){},data:{event_id:id}},waitUntil:p=>pending=p});await pending;
 assert.equal(w.opened[0],'https://preview.example.invalid/?signal_event='+id+'#app-signals');
 for(const bad of [{...data,event_id:'../evil'}, {...data,at:1e100},{...data,score:101}]){
  w.listeners.push({data:{json:()=>bad},waitUntil:p=>pending=p});await pending;
 }
 assert.equal(w.notifications.length,1);
});

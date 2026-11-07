const {test}=require('node:test'),a=require('node:assert/strict'),UI=require('../static/signal-lock-ui.js');
const data={server_time:1000,updated_at:1000,error:null};
const row=(id,status,detected_at=900)=>({id:id.repeat(64),direction:'LONG',status,detected_at,refreshed_at:1000,valid_until:1100});
test('current WATCH/CANDIDATE outrank new terminal history; no historical main card without pin',()=>{
 const dead=row('a','UNKNOWN',999),candidate=row('b','CANDIDATE'),watch=row('c','WATCH',800);
 const rows=UI.ranked([dead,candidate,watch],'LONG',data,1000);
 a.deepEqual(rows.map(r=>r.status),['WATCH','CANDIDATE','UNKNOWN']);
 a.equal(UI.choose(rows,dead.id,false,data,1000),watch);
 a.equal(UI.choose(rows,candidate.id,false,data,1000),candidate);
 a.equal(UI.choose([dead],dead.id,false,data,1000),null);
 a.equal(UI.choose([dead],dead.id,true,data,1000),dead);
});
test('500 fresh updates preserve current selection; expiry/stale/future data fail closed',()=>{
 const old=row('a','WATCH'),newer=row('b','WATCH',999);
 for(let i=0;i<501;i++){const t=1000+i*.01,d={...data,server_time:t,updated_at:t},rows=[{...old,refreshed_at:t},{...newer,refreshed_at:t}];a.equal(UI.choose(UI.ranked(rows,'LONG',d,t),old.id,false,d,t).id,old.id);}
 a.equal(UI.choose([old],old.id,false,data,1100),null);
 a.equal(UI.current(old,{...data,updated_at:1001},1000),'UNKNOWN');
 a.equal(UI.current(old,{...data,error:'STORAGE_UNAVAILABLE'},1000),'UNKNOWN');
});
test('initial checks must never masquerade as the current score explanation',()=>{
 const initial={checks:[{code:'OLD',passed:false}]},current_checks=[{code:'NOW',passed:true}];
 a.deepEqual(UI.scoreChecks({initial,current_checks}),current_checks);
 a.deepEqual(UI.scoreChecks({initial}),[]);
});

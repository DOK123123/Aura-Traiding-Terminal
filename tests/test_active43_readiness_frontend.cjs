'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {view}=require('../static/active43-readiness.js');
const now=1800000030;
function body(){return {scope:'AURA43_ACTIVE_PAPER',market_source:'Bitget · USDT-M Futures / api.bitget.com',strategy_version:'AURA_4.3_ACTIVE_PAPER_3',read_only:true,state_changed:false,paper_only:true,exchange_execution:false,purpose:'OFF_ONLY_ACCOUNT_PRECONDITIONS',read_confirmed:true,last_confirmed_read_at:now,mode:'OFF',open_positions:0,pending:false,pending_exit:false,pending_operations:0,data_recovery_armed:false,risk_guards:{status:'PASS',code:null},scheduler_auth_configured:true,errors:[],status:'PASS'};}
test('verified empty OFF passes; unsafe or incomplete snapshots never pass',()=>{
 assert.equal(view(body(),now).status,'PASS');
 for(const changes of [{mode:'ON'},{mode:'PAUSED'},{mode:'EMERGENCY'},{open_positions:1},{pending:true,pending_operations:1},{pending_exit:true,pending_operations:1},{data_recovery_armed:true},{scheduler_auth_configured:false},{read_confirmed:false},{state_changed:true},{risk_guards:{status:'BLOCKED',code:'DAILY_LOSS_LIMIT'}},{errors:['SERVER_ERROR']},{mode:null},{status:'BLOCKED'}])assert.equal(view({...body(),...changes},now).status,'BLOCKED');
 for(const key of Object.keys(body())){const b=body();delete b[key];assert.equal(view(b,now).status,'BLOCKED',key);}
 assert.equal(view(body(),now+61).status,'BLOCKED');assert.equal(view(body(),now-4).status,'BLOCKED');
 assert.match(view({...body(),risk_guards:{status:'BLOCKED',code:'DAILY_LOSS_LIMIT'}},now).risk,/дневной/);
 assert.doesNotMatch(view({...body(),errors:['PRIVATE_DUMMY_ERROR']},now).reason,/PRIVATE_DUMMY/);
});
function harness(){
 const nodes=new Map(),events={},timers=[];const calls=[];
 const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',disabled:false,addEventListener:(k,fn)=>events[id+':'+k]=fn});return nodes.get(id);};
 let response={ok:true,json:async()=>body()};let time=now;
 class Clock extends Date{static now(){return time*1000;}}
 vm.runInNewContext(fs.readFileSync('static/active43-readiness.js','utf8'),{document:{getElementById:node},window:{addEventListener(){}},Date:Clock,AbortController,setTimeout:()=>1,clearTimeout(){},setInterval:fn=>{timers.push(fn);return 1;},clearInterval(){},fetch:async(path,options)=>{calls.push({path,options});if(response instanceof Error)throw response;return response;}});
 return {nodes,calls,timers,click:()=>events['a43-ro-check:click'](),setResponse:r=>response=r,setTime:t=>time=t};
}
test('click calls only authenticated GET peek route and clears stale PASS on failure',async()=>{
 const h=harness();assert.equal(h.calls.length,0);await h.click();
 assert.equal(h.nodes.get('a43-ro-status').textContent,'PASS');assert.equal(h.calls.length,1);
 assert.equal(h.calls[0].path,'/api/active43/off-only-readiness');assert.equal(h.calls[0].options.method,'GET');assert.equal(h.calls[0].options.cache,'no-store');assert.equal(h.calls[0].options.credentials,'same-origin');
 h.setTime(now+61);h.timers[0]();assert.equal(h.nodes.get('a43-ro-status').textContent,'BLOCKED');
 h.setResponse({ok:false});await h.click();assert.equal(h.nodes.get('a43-ro-status').textContent,'BLOCKED');assert.equal(h.nodes.get('a43-ro-mode').textContent,'Не подтверждено');
 h.setResponse(new Error('PRIVATE_ERROR'));await h.click();assert.doesNotMatch(h.nodes.get('a43-ro-reason').textContent,/PRIVATE_ERROR/);
});
test('new panel is a sibling before legacy load/status panel, not nested within it',()=>{
 const html=fs.readFileSync('static/index.html','utf8');const start=html.indexOf('<details id="active43-off-readiness">'),end=html.indexOf('<details id="active43-panel">');
 assert.ok(start>0&&end>start);assert.ok(html.slice(start,end).includes('</details>'));assert.ok(html.includes('/static/active43-readiness.js'));
});

const {test}=require('node:test');
const assert=require('node:assert/strict');
const {fresh,model}=require('../static/manual-paper.js');
const fs=require('node:fs'),vm=require('node:vm');
const now=1793007900000;
const q={source:'Bitget USDT-M Futures',symbol:'BTCUSDT',product:'USDT-FUTURES',time:now,bid:'80000',ask:'80001'};
const s={mode:'MANUAL_PAPER',virtual_only:true,real_money_execution:'DISABLED',position:null,quote:q,equity:'10000',position_net_pnl:'0'};
test('stale, future and foreign quotes disable actions and conceal current PnL',()=>{
 assert.equal(model(s,now).canOpen,true);
 for(const quote of [{...q,time:now-5001},{...q,time:now+1},{...q,source:'Bybit'},{...q,product:'SPOT'},{...q,ask:'0'},null]){
  const v=model({...s,quote,position:{id:'a'}},now);
  assert.equal(v.canOpen,false);assert.equal(v.canClose,false);assert.equal(v.pnl,null);assert.equal(v.equity,null);
 }
});
test('only one separate virtual position; no real mode accepted',()=>{
 assert.equal(model({...s,position:{id:'a'}},now).canOpen,false);
 assert.equal(model({...s,position:{id:'a'}},now).canClose,true);
 assert.equal(model({...s,real_money_execution:'ENABLED'},now).ok,false);
 assert.equal(model({...s,mode:'ACTIVE43'},now).canOpen,false);
});

// Execute the actual UI script with a minimal DOM. Simulate response loss after
// a server commit, then reload the browser and retry the retained request ID.
function browser(saved,fetch,storageDenied=false){
 const elements=new Map();
 function element(id){if(!elements.has(id))elements.set(id,{id,value:'',textContent:'',disabled:false,hidden:false,open:false,showModal(){this.open=true;},close(){this.open=false;},events:{},addEventListener(k,fn){this.events[k]=fn;},checkValidity(){return true;},reportValidity(){},replaceChildren(){},append(){}});return elements.get(id);}
 const timers=[],events={};
 const context={document:{getElementById:element,hidden:false,addEventListener(k,fn){events[k]=fn;},createElement:()=>element('row'+Math.random())},
  localStorage:{getItem:k=>saved[k]||null,setItem:(k,v)=>{if(storageDenied)throw new Error("storage blocked");saved[k]=v;},removeItem:k=>delete saved[k]},
  navigator:{locks:{request:async(name,options,fn)=>fn({name})}},crypto:{getRandomValues:b=>b.fill(7)},Uint8Array,AbortController,setTimeout,clearTimeout,
  setInterval:fn=>timers.push(fn),addEventListener:(k,fn)=>{events[k]=fn;},structuredClone,fetch,Date,Number,JSON,Error};
 vm.runInNewContext(fs.readFileSync('static/manual-paper.js','utf8'),context);
 return {elements,element,timers,events};
}
const previewResult=()=>({mode:'MANUAL_PAPER',virtual_only:true,real_money_execution:'DISABLED',read_only:true,risk:'5.967006',entry:'80001',quantity:'0.01',stop:'79500',target:'81000',expires_at:Date.now()+30000});
const response=data=>({ok:true,status:200,json:async()=>data});
test('lost response and page reload preserve the exact intent; no duplicate new ID',async()=>{
 const saved={},submitted=[];
 const liveState={...s,quote:{...q,time:Date.now()},trades:[],balance:'10000',realized_pnl:'0'};
 let b=browser(saved,async(path,opt)=>{if(path==='/api/manual-paper/preview')return response(previewResult());if(opt.method==='POST'){submitted.push(JSON.parse(opt.body));throw new Error('response lost');}return response(liveState);});
 b.element('manual-paper-panel').open=true;b.element('manual-paper-panel').events.toggle();await new Promise(r=>setImmediate(r));
 b.element('mp-entry').value='80001';b.element('mp-quantity').value='0.01';b.element('mp-stop').value='79500';b.element('mp-target').value='81000';
 await b.element('mp-long').events.click();assert.equal(submitted.length,0);b.element('mp-confirm').events.click();await new Promise(r=>setImmediate(r));
 assert.equal(submitted.length,1);assert.equal(b.element('mp-long').disabled,true);assert.equal(b.element('mp-retry').hidden,false);
 b=browser(saved,async(path,opt)=>{if(path==='/api/manual-paper/preview')return response(previewResult());if(opt.method==='POST'){submitted.push(JSON.parse(opt.body));return response({request_id:submitted.at(-1).request_id});}return response(liveState);});
 assert.equal(b.element('mp-retry').hidden,false);
 await b.element('mp-retry').events.click();
 assert.deepEqual(submitted[0],submitted[1]);assert.equal(Object.keys(saved).length,0);
});
test('write blocked when confirmed intent cannot be persisted',async()=>{
 let posts=0;const saved={};const b=browser(saved,async(path,opt)=>{if(path==='/api/manual-paper/preview')return response(previewResult());if(opt.method==='POST')posts++;return response({...s,quote:{...q,time:Date.now()},trades:[]});},true);
 b.element('manual-paper-panel').open=true;b.element('manual-paper-panel').events.toggle();await new Promise(r=>setImmediate(r));
 for(const [k,v]of Object.entries({entry:'80001',quantity:'0.01',stop:'79500',target:'81000'}))b.element('mp-'+k).value=v;
 await b.element('mp-long').events.click();assert.equal(b.element('mp-confirm-dialog').open,true);
 b.element('mp-confirm').events.click();await new Promise(r=>setImmediate(r));
 assert.equal(posts,0);assert.match(b.element('mp-status').textContent,/не сохранил/);
});

test('analyst copy, WAIT, cancel and double click never submit an unconfirmed order',async()=>{
 const calls=[],saved={};const b=browser(saved,async(path,opt)=>{calls.push(path);return response(path==='/api/manual-paper/preview'?previewResult():{...s,quote:{...q,time:Date.now()},trades:[]});});
 b.element('manual-paper-panel').open=true;b.element('manual-paper-panel').events.toggle();await new Promise(r=>setImmediate(r));
 const signal={state:'LONG',fresh:true,generated:Date.now()/1000-1,valid_until:Date.now()/1000+59,scenario:{reference_entry:80001,stop_loss:79500,take_profit:81000}};
 b.events['aura-analyst-snapshot']({detail:signal});b.element('mp-copy').events.click();
 assert.equal(b.element('mp-stop').value,'79500');assert.equal(calls.length,1);
 b.element('mp-quantity').value='0.01';await b.element('mp-long').events.click();
 assert.equal(b.element('mp-confirm-dialog').open,true);
 b.element('mp-long').events.click();b.element('mp-cancel').events.click();
 assert.ok(calls.every(p=>!p.endsWith('/orders')));assert.equal(Object.keys(saved).length,0);
 b.events['aura-analyst-snapshot']({detail:{state:'WAIT',fresh:false}});
 assert.equal(b.element('mp-long').disabled,true);assert.equal(b.element('mp-copy').disabled,true);
 b.element('mp-manual').events.click();assert.equal(b.element('mp-long').disabled,false);
});

test('close requires confirmation; visibility/pagehide discard unsent drafts',async()=>{
 const calls=[],b=browser({},async(path,opt)=>{calls.push(path);return response({...s,position:{id:'a'.repeat(32),side:'LONG',quantity:'0.01'},quote:{...q,time:Date.now()},trades:[]});});
 b.element('manual-paper-panel').open=true;b.element('manual-paper-panel').events.toggle();await new Promise(r=>setImmediate(r));
 b.element('mp-close').events.click();assert.equal(b.element('mp-confirm-dialog').open,true);assert.equal(calls.length,1);
 b.events.pagehide();b.element('mp-confirm').events.click();assert.equal(calls.length,1);assert.equal(b.element('mp-confirm-dialog').open,false);
});

test('a pending intent from another tab is never overwritten or submitted as a new operation',async()=>{
 const saved={},sent=[],b=browser(saved,async(path,opt)=>{if(path==='/api/manual-paper/preview')return response(previewResult());if(path.endsWith('/orders'))sent.push(JSON.parse(opt.body));return response({...s,quote:{...q,time:Date.now()},trades:[]});});
 b.element('manual-paper-panel').open=true;b.element('manual-paper-panel').events.toggle();await new Promise(r=>setImmediate(r));
 for(const [k,v]of Object.entries({entry:'80001',quantity:'0.01',stop:'79500',target:'81000'}))b.element('mp-'+k).value=v;
 await b.element('mp-long').events.click();
 const foreign={path:'/api/manual-paper/orders',body:{request_id:'a'.repeat(32),side:'SHORT',quantity:'0.01',stop:'80500',target:'79000'}};
 saved['aura-manual-paper-v1-pending']=JSON.stringify(foreign);
 b.element('mp-confirm').events.click();await new Promise(r=>setImmediate(r));
 assert.equal(sent.length,0);assert.deepEqual(JSON.parse(saved['aura-manual-paper-v1-pending']),foreign);
 assert.equal(b.element('mp-retry').hidden,false);
});

test('corrupt pending storage blocks new commands instead of losing unknown outcomes',async()=>{
 const saved={'aura-manual-paper-v1-pending':'{"broken":true}'},calls=[];
 const b=browser(saved,async(path,opt)=>{calls.push(path);return response({...s,quote:{...q,time:Date.now()},trades:[]});});
 b.element('manual-paper-panel').open=true;b.element('manual-paper-panel').events.toggle();await new Promise(r=>setImmediate(r));
 assert.equal(b.element('mp-long').disabled,true);assert.equal(b.element('mp-close').disabled,true);
 assert.equal(saved['aura-manual-paper-v1-pending'],'{"broken":true}');
});

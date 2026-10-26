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
 function element(id){if(!elements.has(id))elements.set(id,{id,value:'',textContent:'',disabled:false,hidden:false,open:true,events:{},addEventListener(k,fn){this.events[k]=fn;},checkValidity(){return true;},reportValidity(){},replaceChildren(){},append(){}});return elements.get(id);}
 const timers=[];
 const context={document:{getElementById:element,hidden:false,createElement:()=>element('row'+Math.random())},
  localStorage:{getItem:k=>saved[k]||null,setItem:(k,v)=>{if(storageDenied)throw new Error("storage blocked");saved[k]=v;},removeItem:k=>delete saved[k]},
  crypto:{getRandomValues:b=>b.fill(7)},Uint8Array,AbortController,setTimeout,clearTimeout,
  setInterval:fn=>timers.push(fn),fetch,Date,Number,JSON,Error};
 vm.runInNewContext(fs.readFileSync('static/manual-paper.js','utf8'),context);
 return {elements,element,timers};
}
const response=data=>({ok:true,status:200,json:async()=>data});
test('lost response and page reload preserve the exact intent; no duplicate new ID',async()=>{
 const saved={},submitted=[];
 const liveState={...s,quote:{...q,time:Date.now()},trades:[],balance:'10000',realized_pnl:'0'};
 let b=browser(saved,async(path,opt)=>{if(opt.method==='POST'){submitted.push(JSON.parse(opt.body));throw new Error('response lost');}return response(liveState);});
 b.element('manual-paper-panel').events.toggle();await new Promise(r=>setImmediate(r));
 b.element('mp-quantity').value='0.01';b.element('mp-stop').value='79500';b.element('mp-target').value='81000';
 b.element('mp-long').events.click();await new Promise(r=>setImmediate(r));
 assert.equal(submitted.length,1);assert.equal(b.element('mp-long').disabled,true);assert.equal(b.element('mp-retry').hidden,false);
 b=browser(saved,async(path,opt)=>{if(opt.method==='POST'){submitted.push(JSON.parse(opt.body));return response({request_id:submitted.at(-1).request_id});}return response(liveState);});
 assert.equal(b.element('mp-retry').hidden,false);
 await b.element('mp-retry').events.click();
 assert.deepEqual(submitted[0],submitted[1]);assert.equal(Object.keys(saved).length,0);
});
test('write blocked when intent cannot be persisted',async()=>{
 let posts=0;const saved={};const b=browser(saved,async(path,opt)=>{if(opt.method==='POST')posts++;return response({...s,quote:{...q,time:Date.now()},trades:[]});},true);
 b.element('manual-paper-panel').events.toggle();await new Promise(r=>setImmediate(r));
 // Invalid storage object setter throws synchronously during intent persistence.
 Object.preventExtensions(saved);
 b.element('mp-long').events.click();await new Promise(r=>setImmediate(r));
 assert.equal(posts,0);
});

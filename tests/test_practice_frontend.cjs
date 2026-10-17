'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map();function element(id){if(!elements.has(id))elements.set(id,{value:'',disabled:false,textContent:'',children:[],listeners:{},addEventListener(k,f){this.listeners[k]=f;},append(x){this.children.push(x);},replaceChildren(){this.children=[];}});return elements.get(id);}
const requests=[],saved=new Map();let poll=null,position=null,failOnce=true,validationOnce=true,opens=0;
const state=()=>({state:{balance:'10000',fees:'0',realized_pnl:'0',position},available_balance:'8000',error:null,quote_fresh:true,position_pnl_after_exit_costs:null,storage:{backend:'SUPABASE_PRACTICE_ONLY',revision:1,last_saved_at:1800000000},events:[]});
const annotations=[];const fakeSeries={update(){},createPriceLine(p){annotations.push(p);return {};},removePriceLine(){}};
const context={document:{getElementById:element,createElement:()=>({textContent:'',append(){}})},window:{LightweightCharts:{LineSeries:{},createChart:()=>({addSeries:()=>fakeSeries})}},localStorage:{getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)},AbortController,Date,JSON,Number,String,Error,Math,crypto:{randomUUID:()=> '00000000-0000-4000-8000-000000000001'},setTimeout,clearTimeout,setInterval:f=>{poll=f;return 1;},fetch:async(path,options)=>{
  requests.push({path,options});assert.ok(path.startsWith('/api/practice/'));
  if(path.endsWith('/state'))return {ok:true,status:200,json:async()=>state()};
  if(path.endsWith('/quote'))return {ok:true,status:200,json:async()=>({price:'100',time_ms:Date.now(),source:'Binance Spot'})};
  assert.equal(options.headers['X-Aura-Paper'],'local-only');assert.equal(options.credentials,'same-origin');
  if(validationOnce){validationOnce=false;return {ok:false,status:422,json:async()=>({detail:'DUMMY_VALIDATION_ERROR'})};}
  if(failOnce){failOnce=false;return {ok:false,status:503,json:async()=>({code:'STORAGE_TIMEOUT_OUTCOME_UNKNOWN'})};}
  opens++;position={id:'PRACTICE_TEST:manual:id',entry_price:'100.05',stop_loss:'98',take_profit:'104'};
  return {ok:true,status:200,json:async()=>({confirmed:true,duplicate:true,receipt:{kind:'OPEN',id:'practice:cmd:id'},view:state()})};
}};
vm.runInNewContext(fs.readFileSync('static/practice.js','utf8'),context);
const settle=()=>new Promise(r=>setImmediate(r));
(async()=>{
 assert.equal(requests.length,0);assert.equal(element('long').disabled,true);
 element('connect').listeners.click();await settle();await settle();assert.equal(element('long').disabled,false);assert.ok(poll);
 element('long').listeners.click();await settle();await settle();assert.equal(saved.size,0);assert.equal(element('retry').disabled,true);assert.equal(element('long').disabled,false);assert.match(element('status').textContent,/Проверьте SL/);
 element('sl').value='98';element('tp').value='104';element('long').listeners.click();await settle();await settle();
 assert.equal(element('retry').disabled,false);assert.equal(saved.size,1);assert.match(element('status').textContent,/STORAGE_TIMEOUT/);
 const original=JSON.parse(saved.values().next().value);element('retry').listeners.click();await settle();await settle();
 const writes=requests.filter(r=>r.options.method==='POST');assert.equal(writes.length,3);assert.deepEqual(JSON.parse(writes[1].options.body),JSON.parse(writes[2].options.body));
 assert.ok(annotations.some(x=>x.title==='entry_price'&&x.price===100.05));assert.ok(annotations.some(x=>x.title==='stop_loss'&&x.price===98));assert.ok(annotations.some(x=>x.title==='take_profit'&&x.price===104));
 assert.equal(saved.size,0);assert.equal(opens,1);assert.equal(element('long').disabled,true);assert.equal(element('close').disabled,false);
 assert.equal(original.body.direction,'LONG');assert.match(element('status').textContent,/повтор без новой сделки/);
 assert.ok(!fs.readFileSync('static/practice.js','utf8').includes('innerHTML'));
 const beforeTamper=requests.length;saved.set('auraPracticePendingV1',JSON.stringify({path:'/../paper/open',body:{request_id:'DUMMY'}}));
 vm.runInNewContext(fs.readFileSync('static/practice.js','utf8'),context);element('retry').listeners.click();await settle();await settle();
 assert.equal(requests.length,beforeTamper);assert.equal(saved.size,0);assert.match(element('status').textContent,/INVALID_PRACTICE_ACTION/);
 console.log('Paper Practice frontend behavior PASS: auth scope, explicit connect, pending UUID persistence, unknown-outcome retry, no extra trade, chart/position controls.');
})().catch(e=>{console.error(e);process.exitCode=1;});

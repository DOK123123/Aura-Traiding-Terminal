const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {model}=require('../static/live_paper_monitor.js');
const envelope={read_only:true,paper_only:true,exchange_execution:false};
test('no untrusted success',()=>assert.equal(model({status:'VERIFIED'}),null));
test('offline PASS is not live verification',()=>{const r=model({...envelope,status:'WAITING_FOR_REAL_SIGNAL',technical_test:{status:'PASS'}});assert.equal(r.status,'WAITING_FOR_REAL_SIGNAL')});
test('VERIFIED requires linked complete evidence',()=>assert.equal(model({...envelope,status:'VERIFIED',live_cycle_verified:true}).status,'FAILED'));
test('saved complete evidence can be displayed',()=>assert.equal(model({...envelope,status:'VERIFIED',live_cycle_verified:true,verified_cycle:{open:{signal:{event_type:'SIGNAL'}},close:{event_type:'CLOSE_TP'}}}).status,'VERIFIED'));
test('reads only and no execution controls or raw HTML',()=>{const js=fs.readFileSync('static/live_paper_monitor.js','utf8');assert.ok(!/innerHTML|method:|\/tick|\/control|\/positions/.test(js));assert.ok(js.includes("fetch('/api/auto42/live-monitor'"));assert.ok(js.includes('document.hidden'));assert.ok(js.includes('AbortController'));assert.ok(js.includes('if(busy)return'));});

test('actual UI keeps original execution rejection separate from later checks and supports legacy snapshots',async()=>{
 const vm=require('node:vm');
 class Element{constructor(){this.events={};this.children=[];this.textContent='';}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}addEventListener(name,fn){this.events[name]=fn;}}
 const elements=Object.fromEntries(['live-paper-monitor','lpm-results','lpm-status','lpm-refresh'].map(id=>[id,new Element()]));
 let payload={...envelope,status:'WAITING_FOR_REAL_SIGNAL',reason:'NO_VERIFIED_PRODUCTION_CYCLE',events:[],
  execution_rejection:{utc_timestamp:1800000000,reason:'INVALID_STOPS_AT_NEXT_OPEN',scheduler_run_id:'original-run',candle_id:'original-candle'},
  strategy_rejection:{utc_timestamp:1800000900,reason:'MTF_NOT_ALIGNED',scheduler_run_id:'later-run',candle_id:'later-candle'},
  latest_check:{utc_timestamp:1800000900,reason:'MTF_NOT_ALIGNED',strategy_reason:'MTF_NOT_ALIGNED',scheduler_run_id:'later-run',candle_id:'later-candle'}};
 let requests=0;
 const document={getElementById:id=>elements[id],createElement:()=>new Element(),addEventListener(){},hidden:false};
 vm.runInNewContext(fs.readFileSync('static/live_paper_monitor.js','utf8'),{document,AbortController,setTimeout,clearTimeout,setInterval:()=>0,clearInterval(){},fetch:async(url)=>{assert.equal(url,'/api/auto42/live-monitor');requests++;return {status:200,json:async()=>payload}}});
 await elements['lpm-refresh'].events.click();
 let lines=elements['lpm-results'].children.map(e=>e.textContent);
 assert.ok(lines.some(x=>x.includes('Исходный отказ исполнения')&&x.includes('INVALID_STOPS_AT_NEXT_OPEN')&&x.includes('original-run')));
 assert.ok(lines.some(x=>x.includes('Последняя проверка входа')&&x.includes('MTF_NOT_ALIGNED')&&x.includes('later-run')));
 payload={...envelope,status:'WAITING_FOR_REAL_SIGNAL',entry_rejection:{reason:'OLD_STAGE_UNKNOWN'},events:[]};
 await elements['lpm-refresh'].events.click();lines=elements['lpm-results'].children.map(e=>e.textContent);
 assert.ok(lines.some(x=>x.includes('этап не записан')&&x.includes('OLD_STAGE_UNKNOWN')));
 assert.equal(requests,2);
});

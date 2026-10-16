const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {model}=require('../static/live_paper_monitor.js');
const envelope={read_only:true,paper_only:true,exchange_execution:false};
test('no untrusted success',()=>assert.equal(model({status:'VERIFIED'}),null));
test('offline PASS is not live verification',()=>{const r=model({...envelope,status:'WAITING_FOR_REAL_SIGNAL',technical_test:{status:'PASS'}});assert.equal(r.status,'WAITING_FOR_REAL_SIGNAL')});
test('VERIFIED requires linked complete evidence',()=>assert.equal(model({...envelope,status:'VERIFIED',live_cycle_verified:true}).status,'FAILED'));
test('saved complete evidence can be displayed',()=>assert.equal(model({...envelope,status:'VERIFIED',live_cycle_verified:true,verified_cycle:{open:{signal:{event_type:'SIGNAL'}},close:{event_type:'CLOSE_TP'}}}).status,'VERIFIED'));
test('reads only and no execution controls or raw HTML',()=>{const js=fs.readFileSync('static/live_paper_monitor.js','utf8');assert.ok(!/innerHTML|method:|\/tick|\/control|\/positions/.test(js));assert.ok(js.includes("fetch('/api/auto42/live-monitor'"));assert.ok(js.includes('document.hidden'));assert.ok(js.includes('AbortController'));assert.ok(js.includes('if(busy)return'));});

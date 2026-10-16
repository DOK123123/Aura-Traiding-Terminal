const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {model}=require('../static/alignment.js');
test('evidence requires authoritative read-only envelope',()=>{assert.equal(model({snapshot:{schema:'AUTO42_ALIGNMENT_1'}}),null)});
test('missing evidence does not claim a valid block',()=>{assert.deepEqual(model({read_only:true,exchange_execution:false,status:'NOT_CAPTURED'}),{missing:true})});
test('saved rows and production reason are preserved',()=>{const s={schema:'AUTO42_ALIGNMENT_1',strategy_reason:'MTF_NOT_ALIGNED',frames:{'15m':{direction:1},'1h':{direction:-1},'4h':{direction:-1}}};const r=model({read_only:true,exchange_execution:false,status:'CAPTURED',snapshot:s});assert.deepEqual(r.rows.map(x=>x.direction),[1,-1,-1]);assert.equal(r.snapshot.strategy_reason,'MTF_NOT_ALIGNED')});
test('only saved GET evidence, no execution path or HTML injection',()=>{const js=fs.readFileSync('static/alignment.js','utf8');assert.ok(js.includes("fetch('/api/auto42/alignment'"));assert.ok(!/innerHTML|method:|\/tick|\/control|\/positions/.test(js));assert.ok(js.includes('AbortController'));assert.ok(js.includes('finally{clearTimeout'));});

const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {model}=require('../static/execution_verification.js');
test('no fake success without authoritative readonly envelope',()=>{assert.deepEqual(model({isolated:{status:'PASS'}}),[])});
test('live PASS cannot be inferred or accepted from offline test evidence',()=>{const rows=model({read_only:true,live_execution_enabled:false,isolated:{status:'PASS'},historical:{status:'INCONCLUSIVE'},live:{status:'PASS'}});assert.equal(rows[0].status,'PASS');assert.equal(rows[1].status,'INCONCLUSIVE');assert.equal(rows[2].status,'NOT_TESTED')});
test('read-only UI: no account mutation or automatic test trades',()=>{const js=fs.readFileSync('static/execution_verification.js','utf8');assert.ok(!/method:.*POST|\/control|\/tick|\/positions|innerHTML/.test(js));assert.ok(js.includes('if(busy)return'));assert.ok(js.includes('button.disabled=false'));assert.ok(js.includes('AbortController'));});

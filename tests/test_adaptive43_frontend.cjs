const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {safe,names}=require('../static/adaptive43.js');
test('accept research only, never activation evidence',()=>{assert.equal(safe({research_only:true,activation_available:false,real_money_execution:'DISABLED',symbol:'BTCUSDT',runs:[]}),true);assert.equal(safe({research_only:true,activation_available:true}),false)});
test('separate named 4.2, 4.3 and three scenarios',()=>{assert.equal(Object.keys(names).length,5);assert.equal(names.AURA42,'Aura 4.2')});
test('saved GET evidence with no production actions or HTML injection',()=>{const js=fs.readFileSync('static/adaptive43.js','utf8');assert.ok(!/method:|innerHTML|\/api\/auto42|\/control|\/tick|\/positions/.test(js));assert.ok(js.includes('/api/lab/adaptive43'));assert.ok(js.includes('AbortController'));assert.ok(js.includes('strategy_reason'));});

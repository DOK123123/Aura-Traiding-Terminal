const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {view}=require('../static/active43-paper-readiness.js');
const now=1800000150;
function good(){return {scope:'AURA43_ACTIVE_PAPER',market_source:'Bitget · USDT-M Futures / api.bitget.com',strategy_version:'AURA_4.3_ACTIVE_PAPER_3',purpose:'PAPER_START_READINESS',read_only:true,state_changed:false,paper_only:true,exchange_execution:false,production_paper_verified:false,checked_at:now,status:'READY',errors:[],account:{mode:'OFF',open_positions:0,pending:false,pending_exit:false,data_recovery_armed:false,risk_code:null,strategy:'SR_BOUNCE',timeframe:'5m',balance:'10000',realized_pnl:'0',fees:'0',last_confirmed_read_at:now},history:{status:'PASS',source:'Bitget · USDT-M Futures / api.bitget.com',read_only:true,requires_owner_review:false,anchor_status:'MATCHED',checked_at:now},market:{status:'PASS',history_complete:true,bars:1000,last_closed_at:now-now%300,received_at:now,candle_age_seconds:150,request_duration_ms:500},signal:{preview_only:true,direction:null,strategy_reason:'BOUNCE_NO_CONFIRMED_REJECTION',entry_blocker:'AUTO_OFF'},scheduler:{status:'PASS',ticks:[0,1].map(i=>({tick_id:'ACTIVE43_BITGET_'+'a'.repeat(32)+':tick:'+Math.floor((now-i*300)/300),scheduled_at:now-now%300+120-i*300,created_at:now-25-i*300,status:'COMPLETED',mode:'OFF',opened:0,closed:0,state_saved:true}))},events:[]};}
test('READY uses full fresh owner contract and shows OFF rather than claiming activation',()=>{
 const v=view(good(),now);assert.equal(v.status,'READY');assert.match(v.text,/PAPER OFF/);assert.match(v.text,/10000/);assert.match(v.text,/Нет подтверждённого отскока/);
 assert.equal(view(good(),now+61).status,'BLOCKED');assert.equal(view(null,now).status,'BLOCKED');
});
test('unsafe incomplete stale/manual/duplicate data fail closed',()=>{
 for(const mutate of [b=>b.account.mode='ON',b=>b.account.pending=true,b=>delete b.market,b=>b.market.last_closed_at-=300,b=>b.scheduler.ticks[1].tick_id=b.scheduler.ticks[0].tick_id,b=>b.scheduler.ticks[0].state_saved=false,b=>b.errors=['READINESS_READ_FAILED'],b=>b.read_only=false,b=>b.state_changed=true,b=>delete b.signal,b=>delete b.history,b=>b.history.status='BLOCKED',b=>b.history.requires_owner_review=true,b=>b.history.anchor_status='HISTORY_CANDLE_CHANGED']){const b=good();mutate(b);assert.equal(view(b,now).status,'BLOCKED');}
});
test('malicious content never becomes HTML, labels or private output',()=>{
 const b=good();b.errors=['<script>DUMMY_PRIVATE</script>'];b.events=[{kind:'<svg>',created_at:now,reason:'DUMMY?<script>'}];b.signal.entry_blocker='<script>';
 const v=view(b,now);assert.equal(v.status,'BLOCKED');assert.ok(!v.text.includes('<script>'));assert.ok(!v.text.includes('DUMMY_PRIVATE'));
});
test('panel is wired and browser uses only authenticated GET, clears previous READY',()=>{
 const html=fs.readFileSync('static/index.html','utf8'),js=fs.readFileSync('static/active43-paper-readiness.js','utf8');
 assert.match(html,/id="active43-paper-readiness" open/);assert.match(html,/active43-paper-readiness.js/);
 assert.match(js,/fetch\('\/api\/active43\/paper-readiness',\{method:'GET',credentials:'same-origin',cache:'no-store',redirect:'error'/);
 assert.doesNotMatch(js,/\/control|\/tick|\/initialize|\/strategy|innerHTML/);assert.match(js,/snapshot=null;if\(!closed\)render\(\)/);
});
test('history evidence is mandatory even for a READY envelope and displays safe mismatch details',()=>{
 const b=good();b.history={status:'BLOCKED',source:b.market_source,read_only:true,requires_owner_review:true,anchor_status:'HISTORY_CANDLE_CHANGED',code:'HISTORY_CANDLE_CHANGED',changed_fields:['volume','<script>'],change_classification:'DECIMAL_FORMAT_CHANGED',old_ohlcv_hash:'a'.repeat(64),new_ohlcv_hash:'b'.repeat(64)};
 const v=view(b,now);assert.equal(v.status,'BLOCKED');assert.match(v.text,/volume/);assert.match(v.text,/a{64}/);assert.ok(!v.text.includes('<script>'));assert.match(v.text,/владельца/);
});

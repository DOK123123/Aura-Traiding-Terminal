const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs');
const load = () => import('../deploy/active43-free-worker/worker.mjs');
const token = 'DUMMY_CF_ACTIVE43_TOKEN_ONLY_' + 'x'.repeat(40);
const env = operation => ({AURA_ACTIVE43_CRON_ENABLED:'true',AURA_ACTIVE43_OPERATION:operation,
 AURA_ACTIVE43_BITGET_SCHEDULER_SECRET:token});
const good = () => ({scope:'AURA43_ACTIVE_PAPER',strategy_version:'AURA_4.3_ACTIVE_PAPER_3',
 market_source:'Bitget · USDT-M Futures / api.bitget.com',paper_only:true,exchange_execution:false,
 status:'COMPLETED',state_saved:true,mode:'OFF',opened:0,closed:0,processed:false,duplicate:false,
 last_processed_closed_at:null,verification_only:true});
const diagnostic = () => ({...good(),status:'PASS',read_only:true,state_changed:false,production_paper_verified:false,
 bitget:{status:'CONNECTED'},supabase:{status:'CONNECTED'},scheduler:{status:'ACTIVE',diagnostic_delivery_confirmed:true}});
const options = body => ({fetcher:async () => Response.json(body),sleep:async () => {},emit:() => {}});

test('disabled by default: no HTTP, token, account initialization or writes',async () => {
 const {run} = await load();const logs=[];
 await run({}, {fetcher:() => assert.fail('No requests'),emit:b => logs.push(b)});
 assert.equal(logs[0].event,'DISABLED');assert.equal(logs[0].state_changed,false);
});
test('OFF-only fixed auth endpoint and confirmation, no fallback or activation',async () => {
 const {run,default:w} = await load();const logs=[];let calls=0;
 await run(env('off_only'),{emit:b=>logs.push(b),fetcher:async (url,request) => {
  calls++;assert.equal(url,'https://aura-traiding-terminal.onrender.com/api/active43/verify-off-tick');
  assert.equal(request.method,'POST');assert.equal(request.redirect,'manual');
  assert.equal(request.headers['X-Aura-Active43-Bitget-Token'],token);
  assert.equal(request.headers.Origin,undefined);
  assert.deepEqual(JSON.parse(request.body),{confirmation:'INITIALIZE ISOLATED PAPER ACCOUNT'});
  return Response.json(good());
 }});
 assert.equal(calls,1);assert.equal(logs.find(x=>x.event==='TICK_SAVED').event,'TICK_SAVED');
 assert.equal((await w.fetch(new Request('https://not-an-activation.invalid/'))).status,404);
 assert.ok(!JSON.stringify(logs).includes(token));
});
test('saved_mode uses ordinary paper tick and never START/control',async () => {
 const {run} = await load();let calls=0;
 await run(env('saved_mode'),{emit:()=>{},fetcher:async (url,req) => {
  calls++;assert.equal(url,'https://aura-traiding-terminal.onrender.com/api/active43/tick');
  assert.equal(req.body,'');return Response.json({...good(),mode:'ON',opened:1});
 }});assert.equal(calls,1);
});
test('diagnostics validates read-only contract and surfaces BLOCKED without fake readiness',async () => {
 const {run} = await load();let url;const logs=[];
 await run(env('diagnostics'),{emit:b=>logs.push(b),fetcher:async u=>{url=u;return Response.json(diagnostic());}});
 assert.ok(url.endsWith('/diagnostics/scheduler'));assert.equal(logs.find(x=>x.event==='DIAGNOSTICS_RECEIVED').state_changed,false);
 const blockedLogs=[];
 const result=await run(env('diagnostics'),{...options({...diagnostic(),status:'BLOCKED',scheduler:{status:'ERROR',code:'STALE_TICK',diagnostic_delivery_confirmed:true}}),emit:b=>blockedLogs.push(b)});
 assert.deepEqual(result,{status:'BLOCKED',operation:'diagnostics'});
 assert.deepEqual(blockedLogs.map(x=>x.event),['RENDER_REACHED','DIAGNOSTICS_RECEIVED','DIAGNOSTICS_BLOCKED']);
 assert.equal(blockedLogs[1].scheduler_code,'STALE_TICK');
 assert.ok(!blockedLogs.some(x=>x.event==='REQUEST_FAILED'));
 for (const change of [{read_only:false},{state_changed:true},{scope:'AURA42'},{production_paper_verified:true}])
  await assert.rejects(run(env('diagnostics'),options({...diagnostic(),...change})),/INVALID_CONTRACT/);
});
test('unsafe tick contracts and incorrect source never succeed',async () => {
 const {run} = await load();
 for (const change of [{scope:'AURA42'},{market_source:'Binance Spot'},{exchange_execution:true},{paper_only:false},
  {state_saved:false},{opened:2},{processed:true,last_processed_closed_at:null},{processed:true,duplicate:true},
  {last_processed_closed_at:1},{mode:'LIVE'}])
  await assert.rejects(run(env('saved_mode'),options({...good(),...change})),/INVALID_CONTRACT/);
 for (const change of [{mode:'ON'},{opened:1},{closed:1},{verification_only:false}])
  await assert.rejects(run(env('off_only'),options({...good(),...change})),/OFF_ONLY_BOUNDARY/);
});
test('auth, redirects and permanent configuration errors fail once without raw secret leakage',async () => {
 const {run} = await load();
 for (const status of [301,302,307,308,401,403]) {
  let calls=0;const logs=[];
  await assert.rejects(run(env('off_only'),{emit:b=>logs.push(b),fetcher:async()=>{
   calls++;return Response.json({code:token},{status});
  }}));
  assert.equal(calls,1);assert.ok(!JSON.stringify(logs).includes(token));
 }
 let calls=0;
 await assert.rejects(run(env('off_only'),{emit:()=>{},fetcher:async()=>{
  calls++;return Response.json({code:'STORAGE_SCHEMA_MISSING'},{status:503});
 }}),/STORAGE_SCHEMA_MISSING/);assert.equal(calls,1);
});
test('cold start timeout retries same guarded endpoint, accepts duplicate and charges no extra order',async () => {
 const {run} = await load();const urls=[],delays=[];
 await run(env('off_only'),{timeout:5,emit:()=>{},sleep:async ms=>delays.push(ms),fetcher:async(url,req)=>{
  urls.push(url);
  if(urls.length===1)return new Promise((resolve,reject)=>req.signal.addEventListener('abort',()=>reject(Error(token))));
  return Response.json({...good(),duplicate:true});
 }});
 assert.equal(urls.length,2);assert.equal(urls[0],urls[1]);assert.deepEqual(delays,[2000]);
});
test('two bounded network attempts log only safe error codes',async () => {
 const {run} = await load();let calls=0;const logs=[];
 await assert.rejects(run(env('off_only'),{emit:b=>logs.push(b),sleep:async()=>{},fetcher:async()=>{calls++;throw Error(token);}}),/NETWORK_ERROR/);
 assert.equal(calls,2);assert.ok(!JSON.stringify(logs).includes(token));
});
test('saved PAUSED is a known rejection, not retried or reported healthy',async () => {
 const {run} = await load();let calls=0;const logs=[];
 await assert.rejects(run(env('saved_mode'),{emit:b=>logs.push(b),fetcher:async()=>{
  calls++;return Response.json({...good(),status:'PAUSED',mode:'PAUSED',decision:'NETWORK_ERROR'});
 }}),/NETWORK_ERROR/);
 assert.equal(calls,1);assert.equal(logs.find(x=>x.event==='TICK_SAVED').status,'PAUSED');
});
test('Retry-After is respected; excessive or date-based cooldown is not bypassed',async () => {
 const {run} = await load();let calls=0;const delays=[];
 await run(env('off_only'),{emit:()=>{},sleep:async ms=>delays.push(ms),fetcher:async()=>{
  if(++calls===1)return Response.json({code:'RATE_LIMIT'},{status:429,headers:{'Retry-After':'60'}});
  return Response.json(good());
 }});assert.deepEqual(delays,[60000]);
 for (const value of ['999999','Wed, 21 Oct 2026 07:28:00 GMT']) {
  calls=0;await assert.rejects(run(env('off_only'),{emit:()=>{},sleep:async()=>assert.fail('No early retry'),fetcher:async()=>{
   calls++;return Response.json({code:'RATE_LIMIT'},{status:429,headers:{'Retry-After':value}});
  }}));assert.equal(calls,1);
 }
});
test('late, future, wrong cron and exhausted invocations do not dispatch a trading tick',async () => {
 const {run,default:w} = await load();let now=1000000;let calls=0;
 const o={now:()=>now,emit:()=>{},fetcher:async()=>{calls++;throw Error('ignored');}};
 await assert.rejects(run(env('saved_mode'),{...o,scheduledTime:now-240001}),/STALE_TRIGGER/);
 await assert.rejects(run(env('saved_mode'),{...o,scheduledTime:now+3001}),/STALE_TRIGGER/);
 const messages=[];const original=console.log;console.log=s=>messages.push(JSON.parse(s));
 try { await assert.rejects(w.scheduled({cron:'* * * * *',scheduledTime:now},env('saved_mode')),/UNEXPECTED_CRON/); } finally { console.log=original; }
 assert.equal(messages[0].code,'UNEXPECTED_CRON');assert.equal(messages[0].event,'CONFIG_ERROR');
 assert.equal(calls,0);
 await assert.rejects(run(env('saved_mode'),{...o,sleep:async()=>{now+=250000;}}),/INVOCATION_BUDGET_EXCEEDED/);
 assert.equal(calls,1);
});
test('unknown operation or missing/malformed token fails before outbound HTTP',async () => {
 const {run} = await load();const o={fetcher:()=>assert.fail('No HTTP'),emit:()=>{}};
 await assert.rejects(run(env('START'),o),/INVALID_OPERATION/);
 for (const secret of ['',undefined,'short','a'.repeat(300),'a\n'.repeat(40),' '+token,token+' '])
  await assert.rejects(run({...env('off_only'),AURA_ACTIVE43_BITGET_SCHEDULER_SECRET:secret},o),/SCHEDULER_NOT_CONFIGURED/);
});
test('oversized and malformed upstream responses are bounded and never successful',async () => {
 const {run} = await load();
 for (const text of ['x'.repeat(32769),'not JSON']) {
  let calls=0;await assert.rejects(run(env('off_only'),{emit:()=>{},sleep:async()=>{},fetcher:async()=>{
   calls++;return new Response(text);
  }}),/INVALID_RESPONSE/);assert.equal(calls,2);
 }
});
test('free config remains distinct from Aura42 and starts disabled without public routes',async () => {
 const cfg=JSON.parse(fs.readFileSync('deploy/active43-free-worker/wrangler.jsonc','utf8'));
 assert.equal(cfg.vars.AURA_ACTIVE43_CRON_ENABLED,'false');assert.equal(cfg.vars.AURA_ACTIVE43_OPERATION,'diagnostics');
 assert.equal(cfg.workers_dev,false);assert.equal(cfg.preview_urls,false);
 assert.deepEqual(cfg.triggers.crons,['2-59/5 * * * *']);
 assert.ok(!JSON.stringify(cfg).includes(token));assert.equal(cfg.name,'aura-active43-bitget-free-scheduler');
});
test('fast Render loading HTML waits for cold start before second POST',async () => {
 const {run}=await load();let calls=0;const delays=[];
 await run(env('off_only'),{emit:()=>{},sleep:async ms=>delays.push(ms),fetcher:async()=>{
  calls++;return calls===1 ? new Response('<html>Render loading</html>') : Response.json(good());
 }});
 assert.equal(calls,2);assert.deepEqual(delays,[60000]);
});


test('explicit false and invalid operation/secret never dispatch; logs are sanitized',async()=>{
 const {run}=await load();const logs=[];const o={emit:b=>logs.push(b),fetcher:()=>assert.fail('No HTTP')};
 await run({...env('saved_mode'),AURA_ACTIVE43_CRON_ENABLED:'false'},o);
 assert.equal(logs.pop().event,'DISABLED');
 for(const change of [{AURA_ACTIVE43_OPERATION:token},{AURA_ACTIVE43_BITGET_SCHEDULER_SECRET:''},{AURA_ACTIVE43_BITGET_SCHEDULER_SECRET:' '+token}]){
  await assert.rejects(run({...env('off_only'),...change},o));
  const event=logs.pop();assert.equal(event.event,'CONFIG_ERROR');assert.equal(event.http_status,null);assert.equal(event.attempt,0);
  assert.ok(!JSON.stringify(event).includes(token));
 }
});
test('diagnostic transport errors remain errors; every log has safe delivery metadata',async()=>{
 const {run}=await load();
 for(const scenario of [
  {status:401,body:{detail:{code:'SCHEDULER_TOKEN_MISMATCH'}},expected:'SCHEDULER_TOKEN_MISMATCH'},
  {status:403,text:'PRIVATE_DUMMY_UPSTREAM',expected:'HTTP_FORBIDDEN'},
  {status:302,text:token,expected:'REDIRECT_REJECTED'},
  {status:200,body:{...diagnostic(),state_changed:true},expected:'INVALID_CONTRACT'}
 ]){
  const logs=[];let calls=0;
  await assert.rejects(run(env('diagnostics'),{emit:b=>logs.push(b),fetcher:async()=>{
   calls++;return scenario.body?Response.json(scenario.body,{status:scenario.status}):new Response(scenario.text,{status:scenario.status});
  }}),new RegExp(scenario.expected));
  assert.equal(calls,1);assert.equal(logs[0].event,'RENDER_REACHED');
  assert.equal(logs.at(-1).event,'REQUEST_FAILED');assert.equal(logs.at(-1).code,scenario.expected);
  for(const entry of logs){assert.equal(entry.http_status,scenario.status);assert.equal(entry.operation,'diagnostics');assert.equal(entry.attempt,1);}
  assert.ok(!JSON.stringify(logs).includes(token));assert.ok(!JSON.stringify(logs).includes('PRIVATE_DUMMY_UPSTREAM'));
 }
});
test('diagnostic BLOCKED logs safe Supabase stage/codes and never private response fields',async()=>{
 const {run}=await load();const logs=[];
 const result=await run(env('diagnostics'),{...options({...diagnostic(),status:'BLOCKED',virtual_balance:token,current_position:{id:token},supabase:{status:'ERROR',stage:'HISTORY_RPC',code:'STORAGE_PERMISSION_DENIED'},bitget:{status:'ERROR',code:token}}),emit:b=>logs.push(b)});
 assert.equal(result.status,'BLOCKED');const event=logs.find(x=>x.event==='DIAGNOSTICS_RECEIVED');
 assert.equal(event.supabase_code,'STORAGE_PERMISSION_DENIED');assert.equal(event.supabase_stage,'HISTORY_RPC');
 assert.equal(event.bitget_code,'UNCLASSIFIED_SERVER_ERROR');assert.ok(!JSON.stringify(logs).includes(token));
});
test('timeout logs distinguish network, reached Render, and abort without exposing exceptions',async()=>{
 const {run}=await load();const logs=[];
 await assert.rejects(run(env('diagnostics'),{timeout:2,emit:b=>logs.push(b),sleep:async()=>{},fetcher:async(u,r)=>new Promise((resolve,reject)=>r.signal.addEventListener('abort',()=>reject(Error(token))))}),/REQUEST_TIMEOUT/);
 assert.equal(logs.length,2);assert.ok(logs.every(x=>x.event==='REQUEST_FAILED'&&x.http_status===null&&x.code==='REQUEST_TIMEOUT'));
});
test('two isolated off_only cycles preserve OFF and distinguish second saved duplicate',async()=>{
 const {run}=await load();const logs=[];let count=0;
 const o={emit:b=>logs.push(b),fetcher:async()=>Response.json({...good(),duplicate:count++===1})};
 assert.equal((await run(env('off_only'),o)).status,'COMPLETED');assert.equal((await run(env('off_only'),o)).status,'COMPLETED');
 const saves=logs.filter(x=>x.event==='TICK_SAVED');assert.equal(saves.length,2);
 assert.ok(saves.every(x=>x.mode==='OFF'&&x.opened===0&&x.closed===0&&x.state_saved&&x.http_status===200));
 assert.deepEqual(saves.map(x=>x.duplicate),[false,true]);
});
test('actual scheduled handler resolves delivered BLOCKED; disabled handler never fetches',async()=>{
 const {default:worker,CRON}=await load();const messages=[];let calls=0;
 const originalFetch=global.fetch,originalLog=console.log;
 global.fetch=async()=>{calls++;return Response.json({...diagnostic(),status:'BLOCKED'});};
 console.log=value=>messages.push(JSON.parse(value));
 try{
  await worker.scheduled({cron:CRON,scheduledTime:Date.now()},env('diagnostics'));
  assert.equal(calls,1);assert.equal(messages.at(-1).event,'DIAGNOSTICS_BLOCKED');
  await worker.scheduled({cron:CRON,scheduledTime:Date.now()},{...env('off_only'),AURA_ACTIVE43_CRON_ENABLED:'false'});
  assert.equal(calls,1);assert.equal(messages.at(-1).event,'DISABLED');
 }finally{global.fetch=originalFetch;console.log=originalLog;}
});

// Isolated local verification only. No remote destination or real key accepted.
import assert from 'node:assert/strict';
import worker, {CRON} from '../../deploy/active43-free-worker/worker.mjs';
let raw='';for await (const chunk of process.stdin) raw+=chunk;
const input=JSON.parse(raw);
assert.ok(!process.env.RENDER);
assert.match(input.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
assert.ok(input.token.startsWith('DUMMY_'));
assert.ok(Number.isInteger(input.at));
const operation=input.operation || 'off_only';
assert.ok(['off_only','saved_mode'].includes(operation));
const path=operation==='off_only'?'/api/active43/verify-off-tick':'/api/active43/tick';
const nativeFetch=globalThis.fetch,logs=[];
globalThis.fetch=async(url,request)=>{
 assert.equal(url,'https://aura-traiding-terminal.onrender.com'+path);
 assert.equal(request.method,'POST');
 if(operation==='off_only') assert.deepEqual(JSON.parse(request.body),{confirmation:'INITIALIZE ISOLATED PAPER ACCOUNT'});
 else assert.equal(request.body,'');
 return nativeFetch(input.origin+path,request);
};
Date.now=()=>input.at;
console.log=value=>logs.push(typeof value==='string'?JSON.parse(value):value);
await worker.scheduled({cron:CRON,scheduledTime:Math.floor(input.at/300000)*300000+120000},{AURA_ACTIVE43_CRON_ENABLED:'true',
 AURA_ACTIVE43_OPERATION:operation,AURA_ACTIVE43_BITGET_SCHEDULER_SECRET:input.token});
process.stdout.write(JSON.stringify({scope:'LOCAL_HTTP_AND_SQL_NOT_CLOUDFLARE_OR_RENDER',logs}));

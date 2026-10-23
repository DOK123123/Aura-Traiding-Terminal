// Isolated local verification only. No remote destination or real key accepted.
import assert from 'node:assert/strict';
import worker, {CRON} from '../../deploy/active43-free-worker/worker.mjs';
let raw='';for await (const chunk of process.stdin) raw+=chunk;
const input=JSON.parse(raw);
assert.ok(!process.env.RENDER);
assert.match(input.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
assert.ok(input.token.startsWith('DUMMY_'));
assert.ok(Number.isInteger(input.at));
const nativeFetch=globalThis.fetch,logs=[];
globalThis.fetch=async(url,request)=>{
 assert.equal(url,'https://aura-traiding-terminal.onrender.com/api/active43/verify-off-tick');
 assert.equal(request.method,'POST');
 assert.deepEqual(JSON.parse(request.body),{confirmation:'INITIALIZE ISOLATED PAPER ACCOUNT'});
 return nativeFetch(input.origin+'/api/active43/verify-off-tick',request);
};
Date.now=()=>input.at;
console.log=value=>logs.push(typeof value==='string'?JSON.parse(value):value);
await worker.scheduled({cron:CRON,scheduledTime:input.at},{AURA_ACTIVE43_CRON_ENABLED:'true',
 AURA_ACTIVE43_OPERATION:'off_only',AURA_ACTIVE43_BITGET_SCHEDULER_SECRET:input.token});
process.stdout.write(JSON.stringify({scope:'LOCAL_HTTP_AND_SQL_NOT_CLOUDFLARE_OR_RENDER',logs}));

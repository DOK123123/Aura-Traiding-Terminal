// Cloudflare Workers Free scheduler only. No public trigger, account controls,
// exchange methods, Supabase credentials or strategy implementation.
const BASE = 'https://aura-traiding-terminal.onrender.com/api/active43';
export const CRON = '2-59/5 * * * *';
const SOURCE = 'Bitget · USDT-M Futures / api.bitget.com';
const SCOPE = 'AURA43_ACTIVE_PAPER', VERSION = 'AURA_4.3_ACTIVE_PAPER_3';
const HEADER = 'X-Aura-Active43-Bitget-Token';
const CODES = new Set(['SCHEDULER_NOT_CONFIGURED','SCHEDULER_TOKEN_MISSING','SCHEDULER_TOKEN_DUPLICATED',
 'SCHEDULER_TOKEN_MISMATCH','SCHEDULER_ORIGIN_REJECTED','OFF_TICK_REQUIRES_EMPTY_OFF_ACCOUNT',
 'OFF_TICK_ACCOUNT_RISK_BLOCKED','SCHEDULER_ACCOUNT_NOT_INITIALIZED','ACTIVE43_DISABLED',
 'ACTIVE43_BITGET_DISABLED','ACTIVE43_STORAGE_NOT_CONFIGURED','STORAGE_AUTH','STORAGE_PERMISSION_DENIED',
 'STORAGE_SCHEMA_MISSING','STORAGE_UNAVAILABLE','STORAGE_DATABASE_UNAVAILABLE',
 'STORAGE_UNAVAILABLE_OUTCOME_UNKNOWN','STORAGE_TIMEOUT_OUTCOME_UNKNOWN','STORAGE_READ_TIMEOUT',
 'STORAGE_READBACK_OUTCOME_UNKNOWN','CONCURRENT_UPDATE','STALE_EXECUTION_AT_COMMIT',
 'TICK_TIMEOUT_OUTCOME_UNKNOWN','STALE_TICK','NO_CONFIRMED_TICK','SCHEDULER_STORAGE_UNVERIFIED',
 'STALE_DATA','STALE_OR_MISMATCHED_DATA','MISSING_CANDLES','SOURCE_MISMATCH',
 'SOURCE_CORRECTION_OR_HISTORY_MISSING','MARKET_UNAVAILABLE','INVALID_MARKET_DATA',
 'REGION_OR_ACCESS_RESTRICTED','RATE_LIMIT','UPSTREAM_TIMEOUT','NETWORK_ERROR','HTTP_ERROR',
 'UPSTREAM_API_ERROR','UPSTREAM_CLOCK_OR_STALE_RESPONSE','FUTURES_FILTERS_CHANGED',
 'STORAGE_URL_MISSING','STORAGE_URL_INVALID','STORAGE_KEY_MISSING','STORAGE_KEY_INVALID',
 'STORAGE_INVALID_RESPONSE','STORAGE_RESPONSE_LIMIT','STORAGE_RATE_LIMIT','STORAGE_HTTP_ERROR',
 'STORAGE_REDIRECT_BLOCKED','CORRUPT_PORTFOLIO','ACTIVE_SCOPE_OR_CONFIG_MISMATCH','DIAGNOSTIC_TIMEOUT',
 'FUTURES_FILTERS_UNAVAILABLE','DAILY_LOSS_LIMIT','DRAWDOWN_LIMIT','EMERGENCY_STOP','CONFIG_CHANGED']);
const PERMANENT = new Set(['SCHEDULER_NOT_CONFIGURED','SCHEDULER_TOKEN_MISSING','SCHEDULER_TOKEN_DUPLICATED',
 'SCHEDULER_TOKEN_MISMATCH','SCHEDULER_ORIGIN_REJECTED','OFF_TICK_REQUIRES_EMPTY_OFF_ACCOUNT',
 'OFF_TICK_ACCOUNT_RISK_BLOCKED','SCHEDULER_ACCOUNT_NOT_INITIALIZED','ACTIVE43_DISABLED',
 'ACTIVE43_BITGET_DISABLED','ACTIVE43_STORAGE_NOT_CONFIGURED','STORAGE_AUTH','STORAGE_PERMISSION_DENIED',
 'STORAGE_SCHEMA_MISSING','DAILY_LOSS_LIMIT','DRAWDOWN_LIMIT','EMERGENCY_STOP','CONFIG_CHANGED']);
const code = value => typeof value === 'string' && CODES.has(value) ? value : 'UNCLASSIFIED_SERVER_ERROR';
const OPERATIONS = new Set(['diagnostics','off_only','saved_mode']);
const STAGES = new Set(['CONFIGURATION','HISTORY_RPC','ACCOUNT_READ','STATE_VALIDATION','COMPLETE']);
const httpCode = status => status === 401 ? 'HTTP_UNAUTHORIZED' : status === 403 ? 'HTTP_FORBIDDEN' :
 status >= 300 && status < 400 ? 'REDIRECT_REJECTED' : 'INVALID_RESPONSE';
const boolean = value => typeof value === 'boolean';
const identity = b => b && b.scope === SCOPE && b.strategy_version === VERSION &&
 b.market_source === SOURCE && b.paper_only === true && b.exchange_execution === false;

export function tickVerified(b) {
 return identity(b) && b.state_saved === true && ['COMPLETED','PAUSED'].includes(b.status) &&
  ['ON','OFF','PAUSED','EMERGENCY'].includes(b.mode) && boolean(b.processed) && boolean(b.duplicate) &&
  !(b.processed && b.duplicate) && [b.opened,b.closed].every(n => Number.isInteger(n) && n >= 0 && n <= 1) &&
  ((b.last_processed_closed_at === null && !b.processed) ||
   (Number.isInteger(b.last_processed_closed_at) && b.last_processed_closed_at >= 0 && b.last_processed_closed_at % 300 === 0));
}
function diagnosticVerified(b) {
 return identity(b) && b.read_only === true && b.state_changed === false && b.production_paper_verified === false &&
  ['PASS','BLOCKED'].includes(b.status) && b.scheduler?.diagnostic_delivery_confirmed === true &&
  ['CONNECTED','ERROR'].includes(b.bitget?.status) && ['CONNECTED','ERROR'].includes(b.supabase?.status) &&
  ['ACTIVE','ERROR'].includes(b.scheduler?.status);
}
async function readBody(response) {
 const reader = response.body?.getReader();
 if (!reader) throw Error('INVALID_RESPONSE');
 const chunks = []; let size = 0;
 try {
  for (;;) {
   const {done,value} = await reader.read(); if (done) break;
   size += value.length; if (size > 32768) throw Error('RESPONSE_LIMIT'); chunks.push(value);
  }
 } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
 const bytes = new Uint8Array(size); let offset = 0;
 for (const chunk of chunks) { bytes.set(chunk,offset); offset += chunk.length; }
 return JSON.parse(new TextDecoder().decode(bytes));
}

export async function run(env, {fetcher = fetch, sleep = ms => new Promise(r => setTimeout(r,ms)),
 emit = b => console.log(JSON.stringify(b)), now = Date.now, timeout = 120000, scheduledTime = null} = {}) {
 const configuredOperation = env.AURA_ACTIVE43_OPERATION || 'diagnostics';
 // Never log an unvalidated binding (it could accidentally contain a secret).
 const operation = OPERATIONS.has(configuredOperation) ? configuredOperation : null;
 const report = b => emit({component:'ACTIVE43_FREE_SCHEDULER',paper_only:true,exchange_execution:false,
  operation,attempt:0,http_status:null,code:null,...b});
 if (env.AURA_ACTIVE43_CRON_ENABLED !== 'true') {
  report({event:'DISABLED',code:'DISABLED',state_changed:false}); return;
 }
 if (operation === null) {
  report({event:'CONFIG_ERROR',code:'INVALID_OPERATION'}); throw Error('INVALID_OPERATION');
 }
 const token = env.AURA_ACTIVE43_BITGET_SCHEDULER_SECRET;
 if (typeof token !== 'string' || token.length < 32 || token.length > 256 || !/^[\x20-\x7e]+$/.test(token) || token !== token.trim()) {
  report({event:'CONFIG_ERROR',code:'SCHEDULER_NOT_CONFIGURED'}); throw Error('SCHEDULER_NOT_CONFIGURED');
 }
 const start = now();
 if (scheduledTime !== null && (!Number.isInteger(scheduledTime) || scheduledTime > start + 3000 || start - scheduledTime > 240000))
  { report({event:'CONFIG_ERROR',code:'STALE_TRIGGER'}); throw Error('STALE_TRIGGER'); }
 // Finish within four minutes; late deliveries have a smaller window. No replay
 // of prior periods and no unbounded work across subsequent scheduled events.
 const deadline = Math.min(start + 240000, scheduledTime === null ? Infinity : scheduledTime + 270000);
 const path = operation === 'diagnostics' ? '/diagnostics/scheduler' : operation === 'off_only' ? '/verify-off-tick' : '/tick';
 const payload = operation === 'off_only' ? JSON.stringify({confirmation:'INITIALIZE ISOLATED PAPER ACCOUNT'}) : '';
 for (let attempt = 1; attempt <= 2; attempt++) {
  const remaining = deadline - now();
  if (remaining <= 0) { report({event:'REQUEST_FAILED',attempt,code:'INVOCATION_BUDGET_EXCEEDED'}); throw Error('INVOCATION_BUDGET_EXCEEDED'); }
  const abort = new AbortController(), timer = setTimeout(() => abort.abort(),Math.min(timeout,remaining));
  let failure = 'NETWORK_ERROR', status = null, retry = true, delay = 2000;
  try {
   const response = await fetcher(BASE + path,{method:'POST',headers:{[HEADER]:token,'Content-Type':'application/json'},
    body:payload,redirect:'manual',signal:abort.signal});
   status = response.status;
   report({event:'RENDER_REACHED',attempt,http_status:status,code:'HTTP_RESPONSE'});
   retry = [408,409,429,500,502,503,504].includes(status);
   if ([502,503,504].includes(status)) delay = 60000;
   const retryAfter = response.headers.get('Retry-After');
   if (retryAfter !== null) {
    const seconds = /^\d{1,6}$/.test(retryAfter) ? Number(retryAfter) : NaN;
    // Unparseable dates or delays beyond the budget: do not retry too early.
    if (!Number.isFinite(seconds) || seconds * 1000 >= deadline - now()) retry = false;
    else delay = Math.max(delay,seconds * 1000);
   } else if (status === 429) delay = 60000;
   let b;
   try { b = await readBody(response); }
   catch {
    failure = httpCode(status);
    // A waking Render may return HTML immediately instead of holding the POST.
    // Give that cold start time to finish; do not exhaust retries in two seconds.
    if (status === 200) { retry = true; delay = Math.max(delay,60000); }
    throw Error(failure);
   }
   if (status !== 200) {
    failure = code(b?.code || (typeof b?.detail === 'object' ? b.detail?.code : b?.detail));
    if (failure === 'UNCLASSIFIED_SERVER_ERROR' && (status === 401 || status === 403 || status >= 300 && status < 400)) failure = httpCode(status);
    if (PERMANENT.has(failure)) retry = false;
    throw Error(failure);
   }
   retry = false;
   if (operation === 'diagnostics') {
    if (!diagnosticVerified(b)) { failure = 'INVALID_CONTRACT'; throw Error(failure); }
    report({event:'DIAGNOSTICS_RECEIVED',attempt,http_status:status,code:'DIAGNOSTICS_RECEIVED',status:b.status,
     bitget:b.bitget.status,bitget_code:b.bitget.code ? code(b.bitget.code) : null,
     supabase:b.supabase.status,supabase_code:b.supabase.code ? code(b.supabase.code) : null,
     supabase_stage:STAGES.has(b.supabase.stage) ? b.supabase.stage : null,
     scheduler:b.scheduler.status,scheduler_code:b.scheduler.code ? code(b.scheduler.code) : null,state_changed:false});
    if (b.status === 'BLOCKED') report({event:'DIAGNOSTICS_BLOCKED',attempt,http_status:status,
     code:'DIAGNOSTICS_BLOCKED',status:'BLOCKED',state_changed:false});
    // Valid BLOCKED is a delivered read-only result, never trading readiness.
    return {status:b.status,operation};
   }
   if (!tickVerified(b)) { failure = 'INVALID_CONTRACT'; throw Error(failure); }
   if (operation === 'off_only' && (b.verification_only !== true || b.mode !== 'OFF' || b.opened !== 0 || b.closed !== 0)) {
    failure = 'OFF_ONLY_BOUNDARY'; throw Error(failure);
   }
   report({event:'TICK_SAVED',attempt,http_status:status,code:'TICK_SAVED',status:b.status,mode:b.mode,processed:b.processed,duplicate:b.duplicate,
    opened:b.opened,closed:b.closed,state_saved:true});
   if (b.status !== 'COMPLETED') { failure = code(b.decision); throw Error(failure); }
   return {status:'COMPLETED',operation};
  } catch {
   if (abort.signal.aborted && failure === 'NETWORK_ERROR') failure = 'REQUEST_TIMEOUT';
   report({event:'REQUEST_FAILED',attempt,http_status:status,code:failure});
   if (!retry || attempt === 2 || now() + delay >= deadline) throw Error(failure);
  } finally { clearTimeout(timer); }
  await sleep(delay);
 }
}

export default {
 async scheduled(controller,env) {
  if (env.AURA_ACTIVE43_CRON_ENABLED === 'true' && controller.cron !== CRON) {
   console.log(JSON.stringify({component:'ACTIVE43_FREE_SCHEDULER',paper_only:true,exchange_execution:false,
    event:'CONFIG_ERROR',operation:OPERATIONS.has(env.AURA_ACTIVE43_OPERATION || 'diagnostics') ? env.AURA_ACTIVE43_OPERATION || 'diagnostics' : null,
    attempt:0,http_status:null,code:'UNEXPECTED_CRON',expected_cron:CRON}));
   throw Error('UNEXPECTED_CRON');
  }
  await run(env,{scheduledTime:controller.scheduledTime});
 },
 async fetch() { return new Response('Not found',{status:404}); }
};

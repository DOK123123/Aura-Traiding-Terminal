// Scheduler only: no account controls, no exchange endpoints, no public trigger.
const URL='https://aura-traiding-terminal.onrender.com/api/auto42/tick';
const OUTCOMES=new Set(['HEARTBEAT_OFF','NO_NEW_CANDLE','NO_NEW_WORK','CANDLE_PROCESSED','RISK_BLOCKED','DATA_BLOCKED']);
const CODES=new Set(['STALE_DATA','UPSTREAM_TIMEOUT','ANALYSIS_TIMEOUT','NETWORK_ERROR','RATE_LIMIT','STORAGE_TIMEOUT','STORAGE_DNS','STORAGE_CONNECT','STORAGE_AUTH','STORAGE_SCHEMA_MISSING','SCHEDULER_NOT_CONFIGURED','SCHEDULER_AUTH_REQUIRED','CONCURRENT_UPDATE','TICK_TIMEOUT','REQUEST_TIMEOUT','DAILY_LOSS_LIMIT','DRAWDOWN_LIMIT']);
const TRANSIENT=new Set(['UPSTREAM_TIMEOUT','ANALYSIS_TIMEOUT','NETWORK_ERROR','STORAGE_TIMEOUT','STORAGE_DNS','STORAGE_CONNECT','CONCURRENT_UPDATE','TICK_TIMEOUT','REQUEST_TIMEOUT']);
const safeCode=x=>CODES.has(x)?x:'UNCLASSIFIED_SERVER_ERROR';
async function body(response){
 const reader=response.body?.getReader();if(!reader)throw Error('INVALID_RESPONSE');
 const chunks=[];let size=0;
 try {for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>65536)throw Error('RESPONSE_LIMIT');chunks.push(value);}}
 finally {await reader.cancel().catch(()=>{});reader.releaseLock();}
 const bytes=new Uint8Array(size);let at=0;for(const c of chunks){bytes.set(c,at);at+=c.length;}
 return JSON.parse(new TextDecoder().decode(bytes));
}
export async function run(env,{fetcher=fetch,sleep=ms=>new Promise(r=>setTimeout(r,ms)),emit=x=>console.log(JSON.stringify(x)),timeout=120000}={}){
 const token=env.AURA_AUTO42_SCHEDULER_SECRET;
 if(typeof token!=='string'||token.length<32||token.length>256||!/^[\x20-\x7e]+$/.test(token))throw Error('SCHEDULER_NOT_CONFIGURED');
 for(let attempt=1;attempt<=3;attempt++){
  let code='NETWORK_ERROR',status=null,retry=true;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
  try {
   const response=await fetcher(URL,{method:'POST',headers:{'X-Aura-Auto42-Token':token},body:'',redirect:'manual',signal:controller.signal});status=response.status;
   retry=[408,409,429,500,502,503,504].includes(status);
   let data;try {data=await body(response);}catch {code='INVALID_RESPONSE';throw Error(code);}
   if(status!==200){code=safeCode(data?.code||data?.detail);if(['STORAGE_AUTH','STORAGE_SCHEMA_MISSING','SCHEDULER_NOT_CONFIGURED','SCHEDULER_AUTH_REQUIRED'].includes(code))retry=false;throw Error(code);}
   retry=false;
   if(data?.paper_only!==true||data?.exchange_execution!==false){code='SAFETY_BOUNDARY';throw Error(code);}
   if(data.status!=='COMPLETED'){code=safeCode(data.code||data.decision);retry=TRANSIENT.has(code);throw Error(code);}
   if(data.state_saved!==true||typeof data.processed_this_run!=='boolean'||!OUTCOMES.has(data.tick_outcome)||!['ON','OFF','PAUSED','EMERGENCY','ERROR'].includes(data.mode)||
      ![data.opened_positions,data.closed_positions].every(n=>Number.isInteger(n)&&n>=0&&n<=1)||
      (data.tick_outcome==='CANDLE_PROCESSED'&&!data.processed_this_run)||
      (data.processed_this_run&&(!['CANDLE_PROCESSED','RISK_BLOCKED'].includes(data.tick_outcome)||!Number.isInteger(data.last_processed_closed_at)||data.last_processed_closed_at%900!==0))){code='INVALID_CONTRACT';throw Error(code);}
   const result={event:'AUTO42_TICK_CONFIRMED',attempt,outcome:data.tick_outcome,mode:data.mode,processed:data.processed_this_run,opened:data.opened_positions,closed:data.closed_positions};emit(result);return result;
  }catch {
   emit({event:'AUTO42_TICK_FAILED',attempt,http_status:status,code});
   if(!retry||attempt===3)throw Error(code);
  }finally {clearTimeout(timer);}
  await sleep(2000*2**(attempt-1));
 }
}
export default {
 async scheduled(controller,env,ctx){await run(env);},
 async fetch(){return new Response('Not found',{status:404});}
};

const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {view}=require('../static/auto42.js');
function payload(mode='OFF',position=null){return {status:'RECENT_TICK_OBSERVED',revision:1,server_now:100000,fresh:true,scheduler_configured:true,paper_only:true,exchange_execution:false,current_equity:'10001',unrealized_pnl:position?'1':null,win_rate:'50',profit_factor:'1.1',profit_factor_status:'DEFINED',trades:[],state:{mode,position,emergency:mode==='EMERGENCY',balance:'10000',realized_pnl:'0',trades:2,max_drawdown_pct:'0.5',watermark:99900,last_mark_at:99900,last_success_at:99990,last_decision:'NO_CONFIRMED_SETUP'}};}
function harness(fetcher,confirm=true){
 const nodes=new Map();function node(id){if(!nodes.has(id))nodes.set(id,{textContent:'',disabled:false,open:true,children:[],handlers:{},addEventListener(k,f){this.handlers[k]=f;},replaceChildren(){this.children=[];},append(v){this.children.push(v);}});return nodes.get(id);}
 const doc={hidden:false,handlers:{},getElementById:node,createElement:()=>({textContent:''}),addEventListener(k,f){this.handlers[k]=f;}};
 const win={handlers:{},confirm:()=>confirm,addEventListener(k,f){this.handlers[k]=f;}};
 const context={document:doc,window:win,fetch:fetcher,AbortController,Date,Number,Error,JSON,crypto:{randomUUID:()=> 'a'.repeat(32)},setTimeout,clearTimeout,setInterval:()=>1,clearInterval};
 vm.runInNewContext(fs.readFileSync('static/auto42.js','utf8'),context);return {node,doc,win};
}
const response=(body,status=200)=>({ok:status===200,status,json:async()=>body});
test('server OFF ON PAUSED ERROR and EMERGENCY remain distinct',()=>{for(const mode of ['OFF','ON','PAUSED','ERROR','EMERGENCY']){const m=view(payload(mode),false,100010);assert.notEqual(m.mode,'—');assert.equal(m.canStart,mode!=='ON'&&mode!=='EMERGENCY');}});
test('missing storage or data never fabricates balances, equity or active status',()=>{const m=view(null,false,100010);assert.equal(m.balance,'—');assert.equal(m.canStart,false);assert.equal(m.equity,'Нет свежих данных');const stale=view(payload('ON'),true,100010);assert.match(stale.status,/Нет свежих данных/);assert.equal(stale.equity,'Нет свежих данных');});
test('aged server response and hidden-tab return cannot preserve actionable equity',()=>{const m=view(payload('ON'),false,101000);assert.equal(m.equity,'Нет свежих данных');assert.equal(m.unrealized,'Нет свежих данных');});
test('LONG SHORT and no-position cards use actual portfolio data',()=>{for(const direction of ['LONG','SHORT']){const p={direction,entry_price:'100',size:'2',stop_loss:direction==='LONG'?'98':'102',take_profit:direction==='LONG'?'104':'96'};const m=view(payload('ON',p),false,100010);assert.match(m.position,new RegExp(direction));assert.equal(m.unrealized,'1');assert.equal(m.canReset,false);}assert.match(view(payload(),false,100010).position,/Нет открытой/);});
test('closed metrics and current liquidation equity are clearly separate',()=>{const m=view(payload(),false,100010);assert.equal(m.balance,'10 000');assert.equal(m.equity,'10 001');assert.equal(m.realized,'0');assert.equal(m.trades,'2');assert.equal(m.pf,'1,1');});
test('page load makes no request or activation; repeated refresh is single flight',async()=>{let calls=0,release;const gate=new Promise(r=>release=r);const h=harness(async()=>{calls++;await gate;return response(payload());});assert.equal(calls,0);const first=h.node('a42-refresh').handlers.click();await h.node('a42-refresh').handlers.click();assert.equal(calls,1);assert.equal(h.node('a42-refresh').disabled,true);release();await first;assert.equal(h.node('a42-refresh').disabled,false);h.win.handlers.pagehide();});
test('Start requires confirmation and existing protected API; failure never claims ON',async()=>{let calls=[];const h=harness(async(url,opts)=>{calls.push({url,opts});if(opts.method==='POST')return response({code:'DAILY_LOSS_LIMIT'},409);return response(payload());});await h.node('a42-refresh').handlers.click();await h.node('a42-start').handlers.click();const write=calls.find(c=>c.opts.method==='POST');assert.equal(write.url,'/api/auto42/control');assert.equal(write.opts.headers['X-Aura-Paper'],'local-only');assert.equal(JSON.parse(write.opts.body).confirmation,'START PAPER');assert.match(h.node('a42-message').textContent,/Дневной лимит/);assert.doesNotMatch(h.node('a42-mode').textContent,/Включено/);h.win.handlers.pagehide();});
test('declined Start and reset confirmation never write',async()=>{let writes=0;const h=harness(async(url,o)=>{if(o.method==='POST')writes++;return response(payload());},false);await h.node('a42-refresh').handlers.click();await h.node('a42-start').handlers.click();await h.node('a42-reset').handlers.click();assert.equal(writes,0);h.win.handlers.pagehide();});
test('network failures and authorization clear or label prior values, release loading',async()=>{let fail=false;const h=harness(async()=>{if(fail)throw Error('dummy-private-transport-message');return response(payload());});await h.node('a42-refresh').handlers.click();fail=true;await h.node('a42-refresh').handlers.click();assert.equal(h.node('a42-refresh').disabled,false);assert.doesNotMatch(h.node('a42-message').textContent,/dummy-private/);assert.match(h.node('a42-status').textContent,/Нет свежих/);h.win.handlers.pagehide();});
test('mobile accessible controls, warnings and no exchange authority',()=>{const s=fs.readFileSync('static/auto42.js','utf8'),h=fs.readFileSync('static/index.html','utf8'),c=fs.readFileSync('static/auto42.css','utf8');assert.match(h,/АВТОМАТИЧЕСКАЯ ДЕМОТОРГОВЛЯ/);assert.match(h,/REAL MONEY EXECUTION = DISABLED/);assert.match(h,/NO_EDGE_FOUND/);assert.match(c,/min-height:44px/);assert.match(c,/@media\(max-width:430px\)/);assert.match(c,/:focus-visible/);assert.doesNotMatch(s,/innerHTML|X-Aura-Auto42-Token|SUPABASE|API_KEY|bybit|binance|\/order/);});
test('emergency remains available during pending Start and late response cannot repaint it',async()=>{
 let mode='OFF',release;const gate=new Promise(r=>release=r);let starts=0,emergencies=0;
 const h=harness(async(url,opts)=>{
  if(opts.method==='POST'){
   const action=JSON.parse(opts.body).action;
   if(action==='START'){starts++;await gate;return response({paper_only:true,exchange_execution:false});}
   if(action==='EMERGENCY'){emergencies++;mode='EMERGENCY';return response({paper_only:true,exchange_execution:false});}
  }
  return response(payload(mode));
 });
 await h.node('a42-refresh').handlers.click();const start=h.node('a42-start').handlers.click();
 assert.equal(starts,1);assert.equal(h.node('a42-emergency').disabled,false);
 await h.node('a42-emergency').handlers.click();assert.equal(emergencies,1);assert.match(h.node('a42-mode').textContent,/Аварийная/);
 release();await start;assert.match(h.node('a42-mode').textContent,/Аварийная/);h.win.handlers.pagehide();
});

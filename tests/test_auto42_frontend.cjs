const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {view}=require('../static/auto42.js');
function payload(mode='OFF',position=null){return {status:'RECENT_TICK_OBSERVED',revision:1,server_now:100000,fresh:true,scheduler_configured:true,paper_only:true,exchange_execution:false,current_equity:'10001',unrealized_pnl:position?'1':null,win_rate:'50',profit_factor:'1.1',profit_factor_status:'DEFINED',trades:[],state:{mode,position,emergency:mode==='EMERGENCY',balance:'10000',realized_pnl:'0',trades:2,max_drawdown_pct:'0.5',watermark:99900,last_mark_at:99900,last_success_at:99990,last_decision:'NO_CONFIRMED_SETUP'}};}
function harness(fetcher,confirm=true,initialOpen=false){
 const nodes=new Map();function node(id){if(!nodes.has(id))nodes.set(id,{textContent:'',disabled:false,open:true,children:[],handlers:{},addEventListener(k,f){this.handlers[k]=f;},replaceChildren(){this.children=[];},append(v){this.children.push(v);}});return nodes.get(id);}
 const doc={hidden:false,handlers:{},getElementById:node,createElement:()=>({textContent:''}),addEventListener(k,f){this.handlers[k]=f;}};
 node('auto42-panel').open=initialOpen;
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
test('mobile accessible controls, warnings and no exchange authority',()=>{const s=fs.readFileSync('static/auto42.js','utf8'),h=fs.readFileSync('tests/fixtures/legacy_terminal.html','utf8'),c=fs.readFileSync('static/auto42.css','utf8');assert.match(h,/АВТОМАТИЧЕСКАЯ ДЕМОТОРГОВЛЯ/);assert.match(h,/REAL MONEY EXECUTION = DISABLED/);assert.match(h,/NO_EDGE_FOUND/);assert.match(c,/min-height:44px/);assert.match(c,/@media\(max-width:430px\)/);assert.match(c,/:focus-visible/);assert.doesNotMatch(s,/innerHTML|X-Aura-Auto42-Token|SUPABASE|API_KEY|bybit|binance|\/order/);});
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
test('system evidence separates API online from Supabase failure and never invents checks',()=>{
 const {system}=require('../static/auto42.js');const data={diagnostics:{checked_at:100000,render_api:'ONLINE',storage:{status:'ERROR',error_code:'STORAGE_DNS'},auto_paper:'ERROR',protection:'BLOCKED',block_reason:'STORAGE_DNS',last_error:'STORAGE_DNS',configuration:{missing_variables:['AURA_AUTO42_SUPABASE_URL']}}};
 const d=system(data,true,'reply',100010);assert.equal(d.api,'ONLINE');assert.match(d.storage,/ERROR.*DNS/);assert.equal(d.protection,'BLOCKED');assert.equal(d.saved,'—');assert.match(d.config,/AURA_AUTO42_SUPABASE_URL/);
 const stale=system(data,false,'reply',100200);assert.match(stale.api,/UNKNOWN/);assert.equal(stale.storage,'UNKNOWN');
 const noReply=system(data,true,'unknown',100010);assert.match(noReply.api,/UNKNOWN/);assert.equal(noReply.storage,'UNKNOWN');
});
test('failed storage HTTP response is displayed as API available with safe diagnostics',async()=>{
 const now=Math.floor(Date.now()/1000);const h=harness(async()=>response({code:'STORAGE_CONNECT',paper_only:true,exchange_execution:false,diagnostics:{checked_at:now,render_api:'ONLINE',storage:{status:'ERROR',error_code:'STORAGE_CONNECT'},auto_paper:'ERROR',protection:'BLOCKED',block_reason:'STORAGE_CONNECT'}},503));
 await h.node('a42-refresh').handlers.click();assert.equal(h.node('a42-sys-api').textContent,'ONLINE');assert.match(h.node('a42-sys-storage').textContent,/ERROR/);
 assert.match(h.node('a42-status').textContent,/API ответил/);assert.equal(h.node('a42-refresh').disabled,false);h.win.handlers.pagehide();
});
test('all ten system diagnostic items and timestamp timezone are available accessibly',()=>{
 const html=fs.readFileSync('tests/fixtures/legacy_terminal.html','utf8');assert.match(html,/СОСТОЯНИЕ СИСТЕМЫ/);
 for(const name of ['api','storage','scheduler','candle','decision','error','saved','mode','protection','block'])assert.match(html,new RegExp('id="a42-sys-'+name+'"'));
 const {system}=require('../static/auto42.js');const m=system({diagnostics:{last_saved_at:100000}},false,'reply',100010);assert.match(m.saved,/UTC/);assert.equal(m.protection,'UNKNOWN');
});
test('owner connection evidence shows validated active hostname and precise error category',()=>{
 const {system}=require('../static/auto42.js');
 const d={diagnostics:{checked_at:100000,render_api:'ONLINE',storage:{status:'ERROR',error_code:'STORAGE_DNS',error_category:'DNS_ERROR',connection:{hostname:'abcdefghijklmnopqrst.supabase.co'}},protection:'BLOCKED'}};
 const v=system(d,true,'reply',100001);assert.equal(v.host,'abcdefghijklmnopqrst.supabase.co');assert.equal(v.category,'DNS_ERROR');assert.equal(v.api,'ONLINE');assert.equal(v.protection,'BLOCKED');
 d.diagnostics.storage.connection.hostname='https://dummy-secret@host';assert.equal(system(d,true,'reply',100001).host,'—');
});
test('main Auto42 panel precedes separate collapsed Historical Pattern account',()=>{
 const h=fs.readFileSync('tests/fixtures/legacy_terminal.html','utf8');
 assert.ok(h.indexOf('id="auto42-panel"')<h.indexOf('id="paper-legacy-panel"'));
 assert.match(h,/<details id="auto42-panel"[^>]* open>/);
 assert.match(h,/<details id="paper-legacy-panel"[^>]*>/);
 assert.doesNotMatch(h,/<details id="paper-legacy-panel"[^>]*\bopen\b/);
 assert.match(h,/Historical Pattern · прежний Auto Paper/);
 assert.match(h,/Запустить Historical Pattern/);
 assert.match(h,/Запустить Aura 4.2 · START PAPER/);
 assert.equal((h.match(/id="auto42-panel"/g)||[]).length,1);
 assert.equal((h.match(/id="paper-auto-start"/g)||[]).length,1);
});
test('open primary panel reads only Auto42 status on load and reload never activates',async()=>{
 const calls=[];const h=harness(async(url,o)=>{calls.push({url,method:o.method||'GET'});return response(payload('OFF'));},true,true);
 await new Promise(r=>setImmediate(r));
 assert.deepEqual(calls,[{url:'/api/auto42/status',method:'GET'}]);
 assert.match(h.node('a42-mode').textContent,/Выключено/);h.win.handlers.pagehide();
 const second=harness(async(url,o)=>{assert.equal(url,'/api/auto42/status');assert.notEqual(o.method,'POST');return response(payload('ON'));},true,true);
 await new Promise(r=>setImmediate(r));assert.match(second.node('a42-mode').textContent,/Включено/);second.win.handlers.pagehide();
});
test('Auto42 ON and owner OFF are read from same server snapshot without legacy calls',async()=>{
 let mode='OFF';const calls=[];let saved;
 const h=harness(async(url,o)=>{
  calls.push(url);assert.match(url,/^\/api\/auto42\//);
  if(o.method==='POST'){saved=JSON.parse(o.body);mode=saved.action==='START'?'ON':'OFF';return response({paper_only:true,exchange_execution:false});}
  return response(payload(mode));
 });
 await h.node('a42-refresh').handlers.click();await h.node('a42-start').handlers.click();
 assert.equal(saved.action,'START');assert.equal(saved.expected_revision,1);assert.equal(saved.confirmation,'START PAPER');
 assert.match(h.node('a42-mode').textContent,/Включено/);
 await h.node('a42-refresh').handlers.click();assert.match(h.node('a42-mode').textContent,/Включено/);
 await h.node('a42-stop').handlers.click();assert.match(h.node('a42-mode').textContent,/Выключено/);
 assert.ok(calls.every(p=>!p.startsWith('/api/paper/')));h.win.handlers.pagehide();
});
test('legacy mode remains visible on collapsed summary without becoming Auto42 status',()=>{
 const h=fs.readFileSync('tests/fixtures/legacy_terminal.html','utf8');
 const start=h.indexOf('id="paper-legacy-panel"'),end=h.indexOf('</summary>',start);
 assert.ok(h.slice(start,end).includes('id="paper-auto-badge"'));
 assert.equal((h.match(/id="paper-auto-badge"/g)||[]).length,1);
});
test('failed START preserves authoritative OFF balance and diagnostic error through refresh',async()=>{
 const now=Math.floor(Date.now()/1000);const initial=payload('OFF');initial.server_now=now;
 const d={checked_at:now,render_api:'ONLINE',storage:{status:'CONNECTED'},owner_mode:'OFF',auto_paper:'ERROR',protection:'BLOCKED',activation_error:{code:'ANALYSIS_TIMEOUT',mode:'OFF'}};
 const h=harness(async(url,o)=>{
  if(o.method==='POST')return response({...initial,code:'ANALYSIS_TIMEOUT',fresh:false,diagnostics:d},503);
  return response({...initial,diagnostics:d});
 });
 await h.node('a42-refresh').handlers.click();await h.node('a42-start').handlers.click();
 assert.match(h.node('a42-mode').textContent,/Выключено/);assert.match(h.node('a42-balance').textContent,/10/);
 assert.match(h.node('a42-message').textContent,/режим остался OFF/);
 await h.node('a42-refresh').handlers.click();assert.match(h.node('a42-message').textContent,/Последний START отклонён/);assert.match(h.node('a42-mode').textContent,/Выключено/);h.win.handlers.pagehide();
});
test('unknown control timeout with cached OFF never claims activation definitively rejected',async()=>{
 const h=harness(async(url,o)=>o.method==='POST'?response({...payload('OFF'),code:'REQUEST_TIMEOUT',diagnostics:{activation_error:null}},503):response(payload('OFF')));
 await h.node('a42-refresh').handlers.click();await h.node('a42-start').handlers.click();
 assert.doesNotMatch(h.node('a42-message').textContent,/режим остался OFF/);
 assert.match(h.node('a42-message').textContent,/обновите состояние/);h.win.handlers.pagehide();
});

test('fee-inclusive position PnL and signal come from persisted production fields',()=>{
 const p=payload('ON',{direction:'SHORT',entry_price:'100',size:'2',stop_loss:'102',take_profit:'96'});
 p.position_net_pnl='-1.25';p.state.fees='2';p.last_signal={closed_candle_at:99900,reason:'CONFIRMED_STRUCTURE_RETEST',details:{direction:'SHORT'}};
 const v=view(p,false,100010);assert.equal(v.unrealized,'-1,25');assert.equal(v.fees,'2');assert.match(v.signal,/SHORT/);
 assert.equal(view(p,true,100010).unrealized,'Нет свежих данных');
});
test('quote is independent read-only display and never triggers execution',async()=>{
 const p=payload('ON');p.quote_available=true;const calls=[];const now=Date.now();
 const h=harness(async(url,o)=>{calls.push(url);assert.notEqual(o.method,'POST');
  if(url==='/api/auto42/quote')return response({paper_only:true,exchange_execution:false,quote:{price:'68000',time_ms:now}});
  return response(p);
 });
 await h.node('a42-refresh').handlers.click();await new Promise(r=>setImmediate(r));
 assert.deepEqual(calls,['/api/auto42/status','/api/auto42/quote']);assert.match(h.node('a42-quote').textContent,/68/);
 h.win.handlers.pagehide();
});
test('closed trade pagination does not call trading controls and separates epochs',async()=>{
 const p=payload('ON');p.state.epoch='unit';p.history_available=true;p.history_is_partial=true;p.history_cursor=12;
 const calls=[];const h=harness(async(url,o)=>{calls.push(url);assert.notEqual(o.method,'POST');
  return response(url.includes('/trades?')?{paper_only:true,exchange_execution:false,epoch:'unit',trades:[{direction:'LONG',realized_pnl:'2',exit_time:900}],page_may_have_more:false,next_cursor:1}:p);
 });
 await h.node('a42-refresh').handlers.click();assert.equal(h.node('a42-older').disabled,false);
 await h.node('a42-older').handlers.click();assert.match(h.node('a42-history').children[0].textContent,/LONG/);
 assert.equal(h.node('a42-older').disabled,true);assert.deepEqual(calls,['/api/auto42/status','/api/auto42/trades?before=12']);h.win.handlers.pagehide();
});

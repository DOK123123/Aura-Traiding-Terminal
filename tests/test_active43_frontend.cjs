const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {view}=require('../static/active43.js');
function data(mode='OFF'){const now=Math.floor(Date.now()/1000),at=Math.floor(now/900)*900;return {paper_only:true,exchange_execution:false,scope:'AURA43_ACTIVE_PAPER',market_source:'Bitget · USDT-M Futures / api.bitget.com',state:{market_source:'Bitget · USDT-M Futures / api.bitget.com',strategy_version:'AURA_4.3_ACTIVE_PAPER_3',mode,epoch:'ACTIVE43_UNIT',config:{strategy:'DONCHIAN',timeframe:'15m'},balance:'10000',equity:'10000',realized_pnl:'0',fees:'0',slippage:'0',trades:0,max_drawdown_pct:'0',position:null,watermark:at,last_mark_at:at,last_success_at:now,last_run_at:now,last_decision:'NO_SIGNAL',recovery_status:'COLD_START'},server_now:now,current_equity:'10000',scheduler_configured:true,revision:1,trades:[],storage_status:'CONNECTED',restart_readback:true};}
function harness(fetcher,confirmed=true){const nodes=new Map();function node(id){if(!nodes.has(id))nodes.set(id,{textContent:'',disabled:false,open:false,children:[],handlers:{},addEventListener(k,f){this.handlers[k]=f;},replaceChildren(){this.children=[];},append(v){this.children.push(v);}});return nodes.get(id);}const doc={hidden:false,handlers:{},getElementById:node,createElement:()=>({textContent:'',children:[],append(v){this.children.push(v);}}),addEventListener(k,f){this.handlers[k]=f;}};const win={handlers:{},confirm:()=>confirmed,addEventListener(k,f){this.handlers[k]=f;}};const c={document:doc,window:win,fetch:fetcher,AbortController,Date,Number,Math,Error,JSON,crypto:{randomUUID:()=> 'a'.repeat(32)},setTimeout,clearTimeout,setInterval:()=>1,clearInterval};vm.runInNewContext(fs.readFileSync('static/active43.js','utf8'),c);return {node,doc,win};}
const response=(body,status=200)=>({ok:status===200,status,json:async()=>body});
test('absent/unconfigured account never invents starting money or enabled mode',()=>{const v=view(null);assert.equal(v.balance,'—');assert.equal(v.canStart,false);assert.match(v.equity,/Нет свежих/);assert.match(v.live,/не подтверждён/);});
test('OFF ON PAUSED and EMERGENCY are separate owner states',()=>{for(const m of ['OFF','ON','PAUSED','EMERGENCY']){const b=data(m);b.state.emergency=m==='EMERGENCY';const v=view(b);assert.equal(v.canStart,m!=='ON'&&m!=='EMERGENCY');assert.notEqual(v.mode,'—');}});
test('stale response and failures hide equity and position PnL',()=>{const b=data('ON');b.state.position={direction:'LONG',entry_price:'100',size:'2',active_stop:'99',take_profit:'104',entry_time:900};b.position_net_pnl='1';assert.equal(view(b).pnl,'1');assert.match(view(b,true).pnl,/Нет свежих/);assert.match(view(b,false,b.server_now+1000).equity,/Нет свежих/);});
test('LONG and SHORT render actual size, active SL, TP and costs',()=>{for(const direction of ['LONG','SHORT']){const b=data('ON');b.state.position={direction,size:'0.02',entry_price:'68000',active_stop:'67800',stop_loss:'67000',take_profit:'69000',entry_time:900};b.state.fees='2.5';const v=view(b);assert.match(v.position,new RegExp(direction));assert.match(v.position,/67/);assert.equal(v.fees,'2,5');assert.equal(v.canStart,false);}});
test('load and refresh cannot activate any trading mode',async()=>{const calls=[];const h=harness(async(u,o)=>{calls.push([u,o.method]);return response(u.endsWith('/quote')?{paper_only:true,exchange_execution:false,quote:{price:'68000',time_ms:Date.now()},position_id:null}:data());});assert.equal(calls.length,0);await h.node('a43-refresh').handlers.click();await new Promise(r=>setImmediate(r));assert.ok(calls.every(([u,m])=>u.startsWith('/api/active43/')&&m!=='POST'));assert.match(h.node('a43-mode').textContent,/Выключен/);h.win.handlers.pagehide();});
test('START needs experimental confirmation and sends only guarded control',async()=>{const writes=[];const h=harness(async(u,o)=>{if(o.method==='POST')writes.push([u,JSON.parse(o.body),o.headers]);return response(u.endsWith('/quote')?{paper_only:true,exchange_execution:false,quote:{price:'100',time_ms:Date.now()}}:data());});await h.node('a43-refresh').handlers.click();await h.node('a43-start').handlers.click();assert.equal(writes.length,1);assert.equal(writes[0][0],'/api/active43/control');assert.equal(writes[0][1].confirmation,'START EXPERIMENTAL PAPER');assert.equal(writes[0][1].expected_revision,1);assert.equal(writes[0][2]['X-Aura-Paper'],'local-only');h.win.handlers.pagehide();});
test('declined confirmation produces no writes',async()=>{let writes=0;const h=harness(async(u,o)=>{if(o.method==='POST')writes++;return response(data());},false);await h.node('a43-refresh').handlers.click();await h.node('a43-start').handlers.click();assert.equal(writes,0);h.win.handlers.pagehide();});
test('authorization failure clears private prior data',async()=>{let unauthorized=false;const h=harness(async(u,o)=>response(data(),unauthorized?401:200));await h.node('a43-refresh').handlers.click();unauthorized=true;await h.node('a43-refresh').handlers.click();assert.equal(h.node('a43-balance').textContent,'—');assert.match(h.node('a43-message').textContent,/вход владельца/);h.win.handlers.pagehide();});
test('failed control never claims ON or a confirmed trade',async()=>{const h=harness(async(u,o)=>o.method==='POST'?response({code:'STORAGE_TIMEOUT_OUTCOME_UNKNOWN'},503):response(data()));await h.node('a43-refresh').handlers.click();await h.node('a43-start').handlers.click();assert.match(h.node('a43-message').textContent,/не подтверждено/);assert.match(h.node('a43-mode').textContent,/не подтверждено/);h.win.handlers.pagehide();});
test('urgent STOP cannot be overwritten by a late START reply',async()=>{let release,mode='OFF';const gate=new Promise(r=>release=r);const h=harness(async(u,o)=>{if(o.method==='POST'){const a=JSON.parse(o.body).action;if(a==='START'){await gate;return response({paper_only:true,exchange_execution:false});}mode='OFF';return response({paper_only:true,exchange_execution:false});}return response(data(mode));});await h.node('a43-refresh').handlers.click();const start=h.node('a43-start').handlers.click();await h.node('a43-stop').handlers.click();release();await start;assert.match(h.node('a43-mode').textContent,/Выключен/);h.win.handlers.pagehide();});
test('historical panel cannot launch a backtest or set live strategy',()=>{const js=fs.readFileSync('static/active43.js','utf8'),html=fs.readFileSync('static/index.html','utf8'),css=fs.readFileSync('static/active43.css','utf8');assert.match(js,/\/static\/active43-research.json/);assert.doesNotMatch(js,/innerHTML|\/open|\/close|\/signal|\/backtest|SCHEDULER_SECRET|SERVICE_KEY/);assert.match(html,/NO_EDGE_FOUND/);assert.match(html,/Paper SL\/TP не являются биржевыми/);assert.match(css,/min-height:44px/);assert.match(css,/@media\(max-width:430px\)/);assert.match(css,/overflow-x:auto/);});
test('historical summary is public market data, not a live portfolio',()=>{const p=JSON.parse(fs.readFileSync('static/active43-research.json'));assert.equal(p.production_paper_verified,false);assert.equal(p.no_profitability_claim,true);assert.equal(p.candidates.length,15);assert.equal(p.source.futures,false);assert.equal(p.selection.selected_before_final_test,true);});

test('scheduler state is explicit and ages without hiding persisted ON',()=>{const d=data('ON');d.scheduler_status='FRESH';d.last_market_success_at=d.server_now;assert.match(view(d).scheduler,/подтверждён/);const v=view(d,false,d.server_now+400);assert.match(v.scheduler,/не поступают/);assert.equal(v.mode,'Включён');assert.notEqual(v.success,'—');});
test('only Bitget Futures bars and trades enter the separate chart',()=>{const {chartModel}=require('../static/active43.js');const source='Bitget · USDT-M Futures / api.bitget.com',bars=[{time:900,open:'100',high:'102',low:'99',close:'101'},{time:1800,open:'101',high:'103',low:'100',close:'102'}];const d={chart:{source,timeframe:'15m',closed_at:2700,bars},trades:[{market_source:source,entry_time:900,entry_price:'101',exit_time:2700,exit_price:'102',direction:'LONG',exit_reason:'TAKE_PROFIT'},{market_source:'Binance Spot',entry_time:900,entry_price:'99'}]};assert.equal(chartModel(d).marks.length,2);d.chart.source='Binance Spot';assert.equal(chartModel(d),null);d.chart.source=source;d.chart.bars[1].time=1900;assert.equal(chartModel(d),null);});
test('old Spot runtime cannot be displayed or armed as Bitget Futures',()=>{for(const change of [{market_source:'Binance Spot'},{market_source:undefined}]){const d={...data('ON'),...change};const v=view(d);assert.equal(v.canStart,false);assert.match(v.mode,/не подтверждено/);assert.equal(v.balance,'—');}const d=data();d.state.strategy_version='AURA_4.3_ACTIVE_PAPER_1';assert.equal(view(d).canStart,false);});
test('missing production deployment has a clear Russian error and cannot arm',async()=>{const h=harness(async()=>response({detail:'Not Found'},404));await h.node('a43-refresh').handlers.click();assert.match(h.node('a43-message').textContent,/не установлена.*404/);assert.equal(h.node('a43-start').disabled,true);h.win.handlers.pagehide();});

test('one-button diagnostics sends only read-only endpoint even without a portfolio',async()=>{
 const calls=[];const h=harness(async(u,o)=>{calls.push([u,o.method]);return response({paper_only:true,exchange_execution:false,read_only:true,state_changed:false,market_source:'Bitget · USDT-M Futures / api.bitget.com',strategy_version:'AURA_4.3_ACTIVE_PAPER_3',status:'BLOCKED',checked_on_render:false,checked_at:Date.now()/1000,configuration:{server_enabled:false,missing_variables:[],explicit_global_stop:true},bitget:{status:'CONNECTED'},supabase:{status:'CONNECTED',account_status:'NOT_INITIALIZED'},scheduler:{status:'ERROR',code:'NO_CONFIRMED_TICK',last_successful_tick:null},virtual_balance:null,errors:['NO_CONFIRMED_TICK']});});
 await h.node('a43-diagnose').handlers.click();
 assert.deepEqual(calls,[['/api/active43/diagnostics','POST']]);
 assert.equal(h.node('a43-diag-balance').textContent,'—');
 assert.match(h.node('a43-diag-scheduler').textContent,/ERROR/);
 assert.match(h.node('a43-diagnostic-message').textContent,/Render не подтверждён/);
 assert.equal(h.node('a43-start').disabled,true);h.win.handlers.pagehide();
});

test('strategy selector is fail closed unless server confirms empty OFF and guards',()=>{
 const d=data('OFF');Object.assign(d.state,{pending:null,pending_exit:null,data_recovery_armed:false,emergency:false});d.strategy_switch_allowed=true;
 assert.equal(view(d).canSelect,true);
 for(const patch of [{mode:'ON'},{mode:'PAUSED'},{mode:'EMERGENCY'},{position:{}},{pending:{}},{pending_exit:'p'},{data_recovery_armed:true},{emergency:true}]){
  assert.equal(view({...d,state:{...d.state,...patch}}).canSelect,false);
 }
 assert.equal(view({...d,strategy_switch_allowed:false}).canSelect,false);
 assert.equal(view(d,true).canSelect,false);
});
test('owner strategy selection posts only selection, refreshes persisted config and never START',async()=>{
 let chosen=false;const calls=[];
 const h=harness(async(url,options)=>{
  calls.push([url,options]);
  if(options.method==='POST'){
   assert.equal(url,'/api/active43/strategy');const body=JSON.parse(options.body);
   assert.equal(body.choice,'BOUNCE_5M');assert.equal(body.expected_revision,1);
   assert.equal(body.confirmation,'CHANGE PAPER STRATEGY WHILE OFF');chosen=true;
   return response({paper_only:true,exchange_execution:false,state_saved:true});
  }
  const d=data('OFF');Object.assign(d.state,{pending:null,pending_exit:null,data_recovery_armed:false,emergency:false});d.strategy_switch_allowed=true;
  if(chosen){d.state.config={strategy:'SR_BOUNCE',timeframe:'5m'};d.revision=2;}
  return response(d);
 });
 await h.node('a43-refresh').handlers.click();assert.equal(h.node('a43-select-strategy').disabled,false);
 h.node('a43-choice').value='BOUNCE_5M';await h.node('a43-select-strategy').handlers.click();
 assert.match(h.node('a43-strategy').textContent,/SR_BOUNCE 5m/);assert.match(h.node('a43-mode').textContent,/Выключен/);
 assert.equal(calls.filter(x=>x[1].method==='POST').length,1);assert.ok(!calls.some(x=>x[0].endsWith('/control')));
 h.win.handlers.pagehide();
});
test('strategy selection rejected by server is not shown as acknowledged',async()=>{
 const h=harness(async(url,o)=>{
  if(o.method==='POST')return response({code:'STRATEGY_SWITCH_BLOCKED'},503);
  const d=data('OFF');Object.assign(d.state,{pending:null,pending_exit:null,data_recovery_armed:false});d.strategy_switch_allowed=true;return response(d);
 });
 await h.node('a43-refresh').handlers.click();h.node('a43-choice').value='BOUNCE_5M';await h.node('a43-select-strategy').handlers.click();
 assert.match(h.node('a43-message').textContent,/Смена стратегии не подтверждена/);assert.equal(h.node('a43-select-strategy').disabled,true);
 h.win.handlers.pagehide();
});

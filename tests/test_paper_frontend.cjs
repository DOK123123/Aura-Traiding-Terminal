// Offline local paper ledger UI regressions. No server, network or exchange orders.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function environment(answer, initialPending=null) {
  const storage = new Map(initialPending ? [['aura.paper.pending.v1',JSON.stringify(initialPending)]] : []);
  const elements = new Map(), events = new Map(), requests = [], timers = [];
  let reloads = 0;
  let now = 1800000060000, response = answer, fresh = true;
  class Element {
    constructor() { this.textContent='';this.hidden=false;this.disabled=false;this.children=[];this.events={};this.value='';this.dataset={}; }
    append(...children) {this.children.push(...children);}
    replaceChildren(){this.children=[];}
    addEventListener(name,fn){this.events[name]=fn;}
    querySelectorAll(name){return this.children.flatMap(r=>r.children.flatMap(c=>c.children)).filter(e=>e.tag===name);}
    setAttribute(name,value){this[name]=value;}
  }
  const el=name=>{if(!elements.has(name))elements.set(name,new Element());return elements.get(name);};
  el('symbol').value='BTCUSDT';el('paper-reason').value='Offline manual entry';el('paper-direction').value='LONG';
  const selected={dataset:{tf:'1m'}};
  const settings=['starting_balance','commission_pct','risk_per_trade_pct','maximum_position_size_usdt','maximum_simultaneous_positions','stop_loss_pct','take_profit_pct'].map(name=>{const e=new Element();e.dataset.paperSetting=name;return e;});
  const document={hidden:false,getElementById:el,activeElement:null,addEventListener:(name,fn)=>events.set(name,fn),
    querySelector:()=>selected,querySelectorAll:()=>settings,
    createElement:tag=>Object.assign(new Element(),{tag}),createElementNS:(_,tag)=>Object.assign(new Element(),{tag})};
  class Clock extends Date {static now(){return now;}}
  const sandbox={document,location:{reload:()=>{reloads++;}},sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},window:{addEventListener:(name,fn)=>events.set(name,fn)},Date:Clock,
    currentData:{source:'Binance',symbol:'BTCUSDT',timeframe:'1m'},marketIsFresh:()=>fresh,crypto:{randomUUID:()=> '11111111-1111-4111-8111-111111111111'},
    AbortController, setTimeout:()=>1,clearTimeout(){},setInterval:fn=>{timers.push(fn);return 1;},clearInterval(){},
    fetch:async(url,options)=>{requests.push({url,options});if(response instanceof Error)throw response;
      const r=typeof response==='function'?response(url,options):response;
      return {status:r.status||200,ok:(r.status||200)<400,json:async()=>r.body||r};}};
  vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/paper.js'),'utf8'),sandbox);
  const flush=async()=>{for(let i=0;i<15;i++)await Promise.resolve();};
  return {el,requests,events,getReloads:()=>reloads,storage,timers,sandbox,settings,flush,setResponse:r=>{response=r;},setFresh:v=>{fresh=v;},advance:ms=>{now+=ms;},selected};
}
function state(overrides={}) {
 return {paper:true,real_money_execution:'DISABLED',automatic_signal_execution:false,
 settings:{starting_balance:'10000',commission_pct:'0.10',risk_per_trade_pct:'1',maximum_position_size_usdt:'2000',maximum_simultaneous_positions:3,stop_loss_pct:'2',take_profit_pct:'4'},
 statistics:{current_balance:'10000',equity:'10000',net_pnl:'0',win_rate:null,profit_factor:null,maximum_drawdown_pct:'0',open_positions:0,total_trades:0,available_balance:'10000',return_pct:'0',gross_profit:'0',gross_loss:'0',average_win:null,average_loss:null,risk_reward:null,consecutive_wins:0,consecutive_losses:0,total_commissions:'0'},
 open_positions:[],closed_trades:[],closed_trades_total:0,equity_curve:[{equity:'10000'}],equity_curve_total:1,...overrides};
}
function quote(){return {paper:true,real_money_execution:'DISABLED',automatic_signal_execution:false,symbol:'BTCUSDT',timeframe:'1m',source:'Binance',price:'100',candle_time:1800000000,price_time:1800000060000,observed_at:1800000060000};}
async function quoted(env){env.setResponse(quote());await env.el('paper-quote-refresh').events.click();await env.flush();}

test('owner-protected state only on startup, no auto execution',async()=>{const e=environment(state());await e.flush();assert.equal(e.requests.length,1);assert.equal(e.requests[0].url,'/api/paper/state');assert.equal(e.el('paper-data').hidden,false);assert.equal(e.el('paper-open').disabled,true);assert.equal(e.el('paper-metrics').children[4].children[1].textContent,'—');});
test('401 hides ledger and shows owner login',async()=>{const e=environment({status:401});await e.flush();assert.equal(e.el('paper-data').hidden,true);assert.equal(e.el('paper-login').hidden,false);assert.match(e.el('paper-status').textContent,/aura/);});
test('missing owner password does not allow actions',async()=>{const e=environment({status:403});await e.flush();assert.equal(e.el('paper-data').hidden,true);assert.equal(e.el('paper-open').disabled,true);});
test('fresh matched quote enables local-only manual action',async()=>{const e=environment(state());await e.flush();await quoted(e);assert.equal(e.el('paper-open').disabled,false);e.setResponse(url=>url.includes('positions/open')?{id:'local'}:state());e.el('paper-open').events.click();await e.flush();const sent=e.requests.find(r=>r.options.method==='POST');assert.equal(sent.url,'/api/paper/positions/open');assert.equal(sent.options.headers['X-Aura-Paper'],'local-only');assert.equal(JSON.parse(sent.options.body).expected_source,'Binance');assert.equal(JSON.parse(sent.options.body).signal_id,null);assert.ok(e.requests.every(r=>r.url.startsWith('/api/paper/')));});
test('stale quote blocks new entry',async()=>{const e=environment(state());await e.flush();await quoted(e);e.advance(30001);e.timers[0]();assert.equal(e.el('paper-open').disabled,true);});
test('source mismatch blocks paper quote',async()=>{const e=environment(state());await e.flush();e.setResponse({...quote(),source:'Other'});await e.el('paper-quote-refresh').events.click();await e.flush();assert.equal(e.el('paper-open').disabled,true);assert.match(e.el('paper-status').textContent,/источник/);});
test('XAU selected blocks requests for quotes',async()=>{const e=environment(state());await e.flush();e.el('symbol').value='XAUUSD';await quoted(e);assert.equal(e.requests.length,1);assert.equal(e.el('paper-open').disabled,true);});
test('market unavailable invalidates quote',async()=>{const e=environment(state());await e.flush();await quoted(e);e.setFresh(false);e.events.get('market-unavailable')();assert.equal(e.el('paper-open').disabled,true);});
test('timeframe change rejects quote race',async()=>{const e=environment(state());await e.flush();e.setResponse(()=>{e.selected.dataset.tf='5m';return quote();});await e.el('paper-quote-refresh').events.click();await e.flush();assert.equal(e.el('paper-open').disabled,true);});
test('malformed or unsafe state hides controls',async()=>{for(const bad of [state({real_money_execution:'ENABLED'}),state({automatic_signal_execution:true}),state({open_positions:null})]){const e=environment(bad);await e.flush();assert.equal(e.el('paper-data').hidden,true);assert.equal(e.el('paper-open').disabled,true);}});
test('network ambiguity retries the exact request ID, never new trade',async()=>{const e=environment(state());await e.flush();await quoted(e);e.setResponse(new Error('offline'));e.el('paper-open').events.click();await e.flush();assert.equal(e.el('paper-retry').hidden,false);assert.equal(e.el('paper-open').disabled,true);const first=e.requests.at(-1).options.body;e.setResponse(url=>url.includes('positions/open')?{id:'local'}:state());await e.el('paper-retry').events.click();await e.flush();assert.equal(e.requests.filter(r=>r.options.method==='POST').at(-1).options.body,first);assert.equal(e.el('paper-retry').hidden,true);});
test('risk rejection clears pending action without retry',async()=>{const e=environment(state());await e.flush();await quoted(e);e.setResponse({status:409,body:{message:'Risk limit'}});e.el('paper-open').events.click();await e.flush();assert.equal(e.el('paper-retry').hidden,true);assert.match(e.el('paper-status').textContent,/Risk limit/);});
test('journal uses textContent, never HTML injection',async()=>{const trade={exit_time:1800000060000,symbol:'BTCUSDT',direction:'LONG',entry_reason:'<script>bad</script>',exit_reason:'Manual',source:'Binance',timeframe:'1m'};const e=environment(state({closed_trades:[trade],closed_trades_total:1}));await e.flush();assert.equal(e.el('paper-trades').children[0].children[8].textContent,'<script>bad</script>');assert.equal(e.el('paper-trades').children[0].children[8].children.length,0);});
test('equity curve never bridges missing data',async()=>{const e=environment(state({equity_curve:[{equity:'10000'},{equity:null},{equity:'9990'}],equity_curve_total:3}));await e.flush();assert.equal(e.el('paper-curve').children.length,2);});
test('existing position close only hits local ledger',async()=>{const e=environment(state({open_positions:[{id:'paper-id',symbol:'BTCUSDT',direction:'SHORT',data_status:'FRESH'}]}));await e.flush();const button=e.el('paper-positions').querySelectorAll('button')[0];e.setResponse(url=>url.endsWith('/close')?{id:'paper-id'}:state());button.events.click();await e.flush();assert.ok(e.requests.some(r=>r.url==='/api/paper/positions/paper-id/close'));assert.ok(e.requests.every(r=>!r.url.includes('bybit')&&!r.url.includes('binance')));});
test('unknown action survives page refresh without automatic retry',async()=>{const action={path:'positions/open',body:{request_id:'11111111-1111-4111-8111-111111111111',symbol:'BTCUSDT'}};const e=environment(state(),action);await e.flush();assert.equal(e.requests.length,0);assert.equal(e.el('paper-retry').hidden,false);e.setResponse(url=>url.includes('positions/open')?{id:'local'}:state());await e.el('paper-retry').events.click();await e.flush();assert.equal(e.requests[0].options.body,JSON.stringify(action.body));assert.equal(e.storage.size,0);});
test('pending action cannot redirect fetch to any exchange endpoint',async()=>{const e=environment(state(),{path:'https://api.bybit.com/v5/order/create',body:{request_id:'11111111-1111-4111-8111-111111111111'}});await e.flush();assert.equal(e.requests[0].url,'/api/paper/state');assert.equal(e.el('paper-retry').hidden,true);});
test('audit hidden-tab paper snapshot expires instead of displaying old equity',async()=>{const e=environment(state());await e.flush();e.sandbox.document.hidden=true;e.advance(90001);e.timers[0]();assert.equal(e.el('paper-data').hidden,true);assert.equal(e.el('paper-open').disabled,true);assert.match(e.el('paper-status').textContent,/устарел/);assert.equal(e.requests.length,1);});
test('audit bfcache restoration cannot leave paper polling stopped',async()=>{const e=environment(state());await e.flush();e.events.get('pagehide')();const count=e.requests.length;await e.el('paper-refresh').events.click();await e.flush();assert.equal(e.requests.length,count);e.events.get('pageshow')();assert.equal(e.getReloads(),1);assert.equal(e.el('paper-data').hidden,true);});

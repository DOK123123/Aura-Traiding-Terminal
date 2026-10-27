const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {view}=require('../static/aura-analyst.js'),fixture=require('./fixtures/aura_analyst_synthetic.json');
const copy=x=>structuredClone(x),now=fixture.now;
test('LONG/SHORT show only valid read-only closed scenarios; WAIT hides all prices',()=>{
 for(const side of ['LONG','SHORT']){const v=view(fixture[side],now);a.equal(v.state,side);a.ok(v.scenario.net_rr>=1.5);}
 a.equal(view(fixture.WAIT,now).state,'WAIT');a.equal(view(fixture.WAIT,now).scenario,null);
});
test('stale, source mismatch, provisional, malformed levels and missing confirmations fail closed',()=>{
 for(const mutate of [b=>b.source='Spot',b=>b.read_only=false,b=>b.exchange_execution=true,b=>b.manual_only=false,b=>b.frames['5m'].last_closed_at+=300,b=>b.frames['4h'].rsi=NaN,b=>b.scenario.stop_loss=b.scenario.take_profit,b=>b.scenario.net_rr=.5,b=>delete b.cost_model,b=>b.reasons=[],b=>b.fibonacci.high_at=now+3600,b=>delete b.fibonacci]){const b=copy(fixture.LONG);mutate(b);a.equal(view(b,now).state,'WAIT');a.equal(view(b,now).scenario,null);}
 a.equal(view(fixture.LONG,now+61).state,'WAIT');a.equal(view(null,now).scenario,null);
});
test('untrusted reasons never become executable content or public private error text',()=>{
 const b=copy(fixture.WAIT);b.reasons=['<script>DUMMY_INTERNAL</script>'];const v=view(b,now);a.ok(!v.reasons.join('').includes('DUMMY_INTERNAL'));
 const source=fs.readFileSync('static/aura-analyst.js','utf8');a.doesNotMatch(source,/innerHTML|\/api\/active43|\/control|\/tick|\/initialize|\/strategy/);
 a.match(source,/credentials:'omit'/);
});
function browser(){
 const elements=new Map(),handlers={},requests=[],intervals=[],timeouts=new Map();let seq=0,ms=now*1000;
 class Element{constructor(){this.textContent='';this.dataset={};this.children=[];this.hidden=false;this.disabled=false;this.handlers={};}append(...e){this.children.push(...e);}replaceChildren(...e){this.children=e;}addEventListener(k,f){this.handlers[k]=f;}}
 const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
 const document={hidden:false,getElementById:get,createElement:()=>new Element(),addEventListener:(k,f)=>handlers['d:'+k]=f};
 class Clock extends Date{static now(){return ms;}}
 const window={document,addEventListener:(k,f)=>handlers['w:'+k]=f,fetch:(url,options)=>{a.equal(url,'/api/analyst');a.equal(options.method,'GET');let resolve;const p=new Promise(r=>resolve=r);requests.push({resolve,signal:options.signal});return p;}};
 const context=vm.createContext({window,Date:Clock,Intl,Number,Object,Array,AbortController,JSON,console,setInterval:f=>(intervals.push(f),intervals.length),clearInterval(){},setTimeout:f=>(timeouts.set(++seq,f),seq),clearTimeout:i=>timeouts.delete(i)});
 vm.runInContext(fs.readFileSync('static/aura-analyst.js','utf8'),context);
 return {get,document,handlers,requests,advance:n=>{ms+=n*1000;intervals.forEach(f=>f());}};
}
const settle=()=>new Promise(r=>setImmediate(r));
test('background abort and return reject late old response; expiry clears entry/SL/TP',async()=>{
 const b=browser();a.equal(b.requests.length,1);
 b.document.hidden=true;b.handlers['d:visibilitychange']();a.equal(b.requests[0].signal.aborted,true);
 b.document.hidden=false;b.handlers['d:visibilitychange']();a.equal(b.requests.length,2);
 b.requests[1].resolve({ok:true,json:async()=>copy(fixture.LONG)});await settle();a.equal(b.get('analyst-state').textContent,'LONG');
 b.requests[0].resolve({ok:true,json:async()=>copy(fixture.SHORT)});await settle();a.equal(b.get('analyst-state').textContent,'LONG');
 b.advance(61);a.equal(b.get('analyst-state').textContent,'WAIT');a.equal(b.get('analyst-plan').hidden,true);a.equal(b.get('analyst-entry').textContent,'—');
});
test('bfcache pageshow resumes read-only polling',async()=>{const b=browser();b.handlers['w:pagehide']();a.equal(b.requests[0].signal.aborted,true);b.handlers['w:pageshow']({persisted:true});a.equal(b.requests.length,2);});
test('panel and assets are connected to existing terminal',()=>{const html=fs.readFileSync('static/index.html','utf8');a.match(html,/id="aura-analyst"/);a.match(html,/aura-analyst.js/);a.match(html,/aura-analyst.css/);a.match(html,/id="analyst-refresh"/);});

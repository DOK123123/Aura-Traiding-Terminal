const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs');
const journal=require('../static/aura-scenario-journal.js');
const drawings=require('../static/aura-chart-tools.js');
const analyst=require('../static/aura-analyst.js');
const fixture=require('./fixtures/aura_analyst_synthetic.json');
const long={side:'LONG',entry:100,stop:95,target:110,quantity:1};
const short={side:'SHORT',entry:100,stop:105,target:90,quantity:1};
class Storage{constructor(){this.data=new Map();this.writes=0;}getItem(k){return this.data.get(k)??null;}setItem(k,v){this.data.set(k,v);this.writes++;}}

test('independent LONG/SHORT costs use adverse fills, double-sided fees and correct signs',()=>{
 const l=journal.estimate(long,110),s=journal.estimate(short,90);
 a.equal(l.entryFill,100.05);a.equal(l.exitFill,109.945);a.equal(l.fees,.209995);a.equal(l.net,9.685005);a.equal(l.slippage,.105);
 a.equal(s.entryFill,99.95);a.equal(s.exitFill,90.045);a.equal(s.fees,.189995);a.equal(s.net,9.715005);a.equal(s.slippage,.095);
 a.ok(journal.estimate(long,95).net<0);a.ok(journal.estimate(short,105).net<0);
});
test('hypothetical risk, geometry, finite decimal and notional limits fail closed',()=>{
 for(const p of [{...long,quantity:25},{...long,stop:90,quantity:6},{...long,target:99},{...long,entry:Infinity},{...long,quantity:-1},{...short,stop:90},{...long,entry:true}])a.throws(()=>journal.validatePlan(p));
 for(const n of ['NaN','-0.1','1e5','1.000000000',' 10','01',null,true,0])a.throws(()=>journal.units(n));
 a.doesNotThrow(()=>journal.validatePlan({...long,quantity:.001}));
});
test('journal persists only to its separate namespace and restores immutable plans/results',()=>{
 const store=new Storage(),r=journal.record(long,'scenario-1',1800000000,'5m','<script>not executable</script>');
 let rows=journal.append([],r);rows=journal.append(rows,r);a.equal(rows.length,1);
 a.equal(store.writes,0);journal.write(store,rows);a.equal(store.writes,1);
 a.deepEqual(journal.read(store),rows);a.deepEqual([...store.data.keys()],[journal.KEY]);
 const reviewed=journal.review(journal.read(store),'scenario-1',110,1800000300);journal.write(store,reviewed);
 const restored=journal.read(store);a.equal(restored[0].state,'REVIEWED');a.equal(journal.estimate(restored[0].plan,restored[0].exit).net,9.685005);
 a.throws(()=>journal.review(restored,'scenario-1',120,1800000600));
 a.throws(()=>journal.review(rows,'unknown',120,1800000600));
 a.throws(()=>journal.review(rows,'scenario-1',120,1700000000));
});
test('malformed, duplicate, oversized storage is rejected without writing or clearing',()=>{
 const store=new Storage();store.setItem(journal.KEY,'{broken');const before=store.writes;
 a.throws(()=>journal.read(store));a.equal(store.writes,before);a.equal(store.getItem(journal.KEY),'{broken');
 a.throws(()=>journal.write(store,Array(201).fill(journal.record(long,'x',1800000000,'5m'))));
 a.throws(()=>journal.record(long,'x',1800000000,'5m','x'.repeat(281)));
 a.throws(()=>journal.record(long,'x',Number.MAX_SAFE_INTEGER,'5m'));
 const r=journal.record(long,'x',1800000000,'5m');
 store.setItem(journal.KEY,JSON.stringify({version:1,entries:[r,r]}));a.throws(()=>journal.read(store));
});
test('drawings: causal timestamps are user coordinates, all tools and handles persist without price edits',()=>{
 const p={time:1800000000,price:100},q={time:1800000300,price:110};
 const all=['horizontal','trend','zone','fib','plan'].map((type,i)=>drawings.cleanShape({id:'d'+i,type,points:type==='horizontal'?[p]:type==='plan'?[p,{...p,price:95},q]:[p,q],side:'LONG'}));
 const raw=JSON.stringify({version:1,frames:{'5m':all,'15m':[]}});
 a.deepEqual(drawings.decode(raw).frames['5m'],all);
 a.equal(drawings.movePoint(all[1],1,{...q,price:120}).points[1].price,120);a.equal(all[1].points[1].price,110);
 a.deepEqual(drawings.fibLevels(p,q).map(r=>r.price),[110,107.64,106.18,105,103.82,102.14,100]);
 a.equal(drawings.fibLevels(q,p)[1].price,102.36);
});
test('drawings reject poison keys, invalid shapes, hidden account data and limits',()=>{
 for(const raw of ['{bad',JSON.stringify({version:1,frames:{'__other':[]}}),JSON.stringify({version:1,frames:{'5m':Array(41).fill({})}})])a.throws(()=>drawings.decode(raw));
 a.throws(()=>drawings.cleanShape({id:'x',type:'order',points:[]}));
 a.throws(()=>drawings.cleanShape({id:'x',type:'horizontal',points:[{time:1800000000,price:NaN}]}));
 a.throws(()=>drawings.movePoint({id:'x',type:'horizontal',points:[{time:1800000000,price:100}]},-1,{time:1800000000,price:90}));
 const safe=drawings.cleanShape({id:'x',type:'horizontal',points:[{time:1800000000,price:100,secret:'DUMMY'}],private:'DUMMY'});a.ok(!JSON.stringify(safe).includes('DUMMY'));
});
test('technical evidence exposes support/conflict without using provisional bars',()=>{
 const v=analyst.view(fixture.LONG,fixture.now),context=analyst.contextEvidence(v.frames,v.state);
 a.ok(context.items.some(e=>e.relation==='SUPPORTS'));a.ok(context.items.every(e=>['5m','15m','1h','4h'].includes(e.tf)));
 const f=structuredClone(v.frames['5m']);f.technical.macd.bias='SHORT';
 a.ok(analyst.contextEvidence({...v.frames,'5m':f},'LONG').items.some(e=>e.name==='MACD histogram'&&e.relation==='CONFLICTS'));
 const bad=structuredClone(v.frames['5m']);bad.technical.swings=[{kind:'LOW',price:10,time:fixture.now,confirmed_at:fixture.now+900}];
 a.equal(analyst.technicalView(bad,'5m'),null);
 bad.technical.swings=[null];a.equal(analyst.technicalView(bad,'5m'),null);
 bad.technical.swings=[];bad.technical.rsi_divergences=[null];a.equal(analyst.technicalView(bad,'5m'),null);
 a.deepEqual(analyst.contextEvidence(analyst.view(fixture.LONG,fixture.now+100).frames,'WAIT').items,[]);
});
test('manual modules have no network/account/auto-paper hooks or HTML interpolation',()=>{
 for(const path of ['static/aura-chart-tools.js','static/aura-scenario-journal.js']){
  const s=fs.readFileSync(path,'utf8');a.doesNotMatch(s,/\bfetch\s*\(|XMLHttpRequest|WebSocket|\/api\/|innerHTML|\.submit\(/);
  a.doesNotMatch(s,/market-data-changed['"],?\s*\{detail/);
 }
 const html=fs.readFileSync('static/index.html','utf8');a.match(html,/id="drawing-tool"/);a.match(html,/id="journal-save"/);
 a.match(fs.readFileSync('static/app.js','utf8'),/AuraChartTools\?\.attach/);
});
test('exclusive journal lock rejects stale tab overwrite and no-lock browsers cannot write',async()=>{
 const store=new Storage();let chain=Promise.resolve();const locks={request:(_key,_opts,f)=>{const p=chain.then(f);chain=p.catch(()=>{});return p;}};
 const r=journal.record(long,'race-1',1800000000,'5m');
 const results=await Promise.allSettled([journal.mutate(store,locks,[],rows=>journal.append(rows,r)),journal.mutate(store,locks,[],rows=>journal.append(rows,{...r,id:'race-2'}))]);
 a.equal(results.filter(r=>r.status==='fulfilled').length,1);a.equal(journal.read(store).length,1);a.equal(store.writes,1);
 const before=store.writes;await a.rejects(journal.mutate(store,null,journal.read(store),r=>r));a.equal(store.writes,before);
});

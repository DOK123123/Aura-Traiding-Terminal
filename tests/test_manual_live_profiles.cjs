const {test}=require('node:test'),a=require('node:assert/strict'),A=require('../static/manual-live-analysis.js'),{Model}=require('../research/live_manual/profiles/model.cjs'),fixture=require('./fixtures/manual_live_synthetic.json'),P=require('../research/live_manual/profiles/protocol.json');
const copy=x=>structuredClone(x),now=fixture.now;
function conflict(lowCost=false){const s=copy(fixture.snapshots.LONG);s.windows['4h']=copy(fixture.snapshots.SHORT.windows['4h']);if(lowCost){for(const w of Object.values(s.windows))for(const b of w.bars)for(const k of ['open','high','low','close'])b[k]-=10000;for(const k of ['bid','ask','last'])s.quote[k]-=10000;}return s;}
test('4h conservative veto is explicit; moderate warning requires extra strength and RR, never automatic override',()=>{
 const s=conflict(true),views=A.analyzeProfiles(s,now);a.equal(views.CONSERVATIVE.state,'WAIT');a.equal(views.CONSERVATIVE.reasons[0],'CONFLICTING_4H');a.ok(views.CONSERVATIVE.blockers.includes('CONFLICTING_4H'));a.deepEqual(views.CONSERVATIVE.hard_blocks,[]);
 const m=views.MODERATE;a.equal(m.state,'LONG',JSON.stringify(m.blockers));a.ok(m.warnings.includes('CONFLICTING_4H'));a.ok(!m.blockers.includes('CONFLICTING_4H'));a.equal(m.scenario.min_net_rr,2);a.ok(m.scenario.net_rr>=2);
 const expensive=A.analyzeProfiles(conflict(),now).MODERATE;a.equal(expensive.state,'WAIT');a.ok(expensive.blockers.includes('INSUFFICIENT_RR_AFTER_COSTS'));
 for(const b of s.windows['1h'].bars){b.open=b.close=4000;b.high=4030;b.low=3970;}
 const weak=A.analyzeProfiles(s,now).MODERATE;a.equal(weak.state,'WAIT');a.ok(weak.blockers.includes('COUNTER_4H_STRENGTH_REQUIRED'));
});
test('all unmet conditions are visible even when legacy returns its first 4h rejection',()=>{
 const s=conflict();s.windows['5m'].bars.at(-1).volume=0;const v=A.analyzeProfiles(s,now).CONSERVATIVE;a.ok(v.blockers.includes('CONFLICTING_4H'));a.ok(v.blockers.includes('PARTIAL_VOLUME_NOT_SUPPORTING'));a.equal(v.reasons[0],'CONFLICTING_4H');a.equal(v.potentials.length,2);
 for(const p of v.potentials){a.equal(p.conditional_only,true);a.ok(p.checks.every(x=>x.kind==='ENTRY_CONDITION'));a.ok(p.conditions_met<=p.conditions_total);}
});
test('both profiles keep identical fail-closed freshness/source/history guards and clear potential plans',()=>{
 for(const mutate of [s=>s.quote.time-=6,s=>s.quote.received_at=now+1,s=>s.status='STALE',s=>s.quote.source='SPOT',s=>delete s.windows['1h'],s=>s.windows['5m'].bars.splice(40,1),s=>s.windows['4h'].event_at-=11]){const s=copy(fixture.snapshots.LONG);mutate(s);for(const v of Object.values(A.analyzeProfiles(s,now))){a.equal(v.state,'WAIT');a.equal(v.scenario,null);a.ok(v.hard_blocks.length);a.deepEqual(v.potentials,[]);a.equal(v.nearest,null);}}
});
test('conservative direction matches legacy LONG/SHORT/WAIT; effective zone contains an accepted quote',()=>{
 for(const side of ['LONG','SHORT']){const s=fixture.snapshots[side],v=A.analyze(s,now);a.equal(v.state,A.legacyAnalyze(s,now).state);a.ok(v.scenario.entry_zone.low<=v.scenario.reference_entry&&v.scenario.reference_entry<=v.scenario.entry_zone.high);const m=A.analyze(s,now,'MODERATE');a.equal(m.state,side);a.ok(m.warnings.includes('TARGET_IS_PROJECTION'));}
 const bad=A.analyze(fixture.snapshots.LONG,now,'anything');a.equal(bad.state,'WAIT');a.deepEqual(bad.hard_blocks,['INVALID_PROFILE']);
});
test('potential LONG and SHORT conditions remain informational and causal; profile change is journalled',()=>{
 const s=copy(fixture.snapshots.LONG);s.windows['5m'].bars.at(-1).volume=0;const v=A.analyze(s,now);a.equal(v.state,'WAIT');a.ok(v.nearest);a.ok(v.potentials.some(p=>p.side==='LONG'&&p.scenario));const before=copy(v.potentials);s.windows['5m'].bars.push({...s.windows['5m'].bars.at(-1),time:now+300});a.deepEqual(A.analyze(s,now,'MODERATE').potentials,[]);a.deepEqual(v.potentials,before);
 const h=new A.History();h.add(v);h.add({...v,profile:'MODERATE'});a.equal(h.items.length,2);a.equal(h.items[1].profile,'MODERATE');
});
test('offline model cannot use future candle close to free a position before a signal; SL-first and repeat suppression',()=>{
 const m=new Model(P),plan={state:'LONG',scenario:{entry_zone:{low:90,high:110},stop_loss:96,take_profit:110,min_net_rr:1.5}};
 m.signal(plan,1800000003,'x','RANGE');m.atOpen({time:1800000120,open:100,volume:1});a.ok(m.position);m.signal(plan,1800000123,'y','RANGE');a.equal(m.pending,null);
 m.atClose({time:1800000120,open:100,high:115,low:90,close:102,volume:1});a.equal(m.trades[0].reason,'STOP_LOSS');a.equal(m.position,null);m.signal(plan,1800000183,'x','RANGE');a.equal(m.pending,null);
});
test('offline adverse spread/slippage, bilateral fees and cash agree with an independent known result',()=>{
 const m=new Model(P),plan={state:'LONG',scenario:{entry_zone:{low:90,high:110},stop_loss:96,take_profit:110,min_net_rr:1.5}};m.signal(plan,1800000003,'x','RANGE');m.atOpen({time:1800000120,open:100,volume:1});const p=m.position;a.ok(p);m.atClose({time:1800000120,open:100,high:111,low:99,close:110,volume:1});const exit=110*.9994,entry=100*1.0006,expected=(exit-entry)*p.quantity-(exit+entry)*p.quantity*.001;a.ok(Math.abs(m.cash-(10000+expected))<1e-8);a.ok(Math.abs(m.trades[0].net-expected)<1e-8);
});
test('offline pending withdrawal, zero prints, high costs and day/drawdown guards block openings',()=>{
 const plan={state:'LONG',scenario:{entry_zone:{low:90,high:110},stop_loss:96,take_profit:110,min_net_rr:1.5}},m=new Model(P);m.signal(plan,1800000003,'x','RANGE');m.signal({state:'WAIT'},1800000063,'z','RANGE');a.equal(m.pending,null);
 m.signal(plan,1800000063,'y','RANGE');m.atOpen({time:1800000240,open:100,volume:0});a.equal(m.position,null);
 const dd=new Model(P);dd.cash=9000;dd.signal(plan,1800000003,'z','RANGE');dd.atOpen({time:1800000120,open:100,volume:1});a.equal(dd.position,null);
});
test('SHORT has mirrored 4h warning conditions and independent adverse-fill accounting',()=>{
 const s=copy(fixture.snapshots.SHORT);s.windows['4h']=copy(fixture.snapshots.LONG.windows['4h']);for(const w of Object.values(s.windows))for(const b of w.bars)for(const k of ['open','high','low','close'])b[k]-=10000;for(const k of ['bid','ask','last'])s.quote[k]-=10000;
 const v=A.analyzeProfiles(s,now);a.equal(v.CONSERVATIVE.state,'WAIT');a.equal(v.MODERATE.state,'SHORT');a.ok(v.MODERATE.warnings.includes('CONFLICTING_4H'));a.ok(v.MODERATE.scenario.net_rr>=2);
 const m=new Model(P),plan={state:'SHORT',scenario:{entry_zone:{low:90,high:110},stop_loss:104,take_profit:90,min_net_rr:1.5}};m.signal(plan,1800000003,'short','TREND_DOWN');m.atOpen({time:1800000120,open:100,volume:1});const q=m.position.quantity;m.atClose({time:1800000120,open:100,high:101,low:89,close:90,volume:1});const e=100*.9994,x=90*1.0006,net=(e-x)*q-(e+x)*q*.001;a.ok(Math.abs(m.cash-10000-net)<1e-8);a.equal(m.trades[0].reason,'TAKE_PROFIT');
});

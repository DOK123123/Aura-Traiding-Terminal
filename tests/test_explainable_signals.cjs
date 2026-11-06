'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const E=require('../static/explainable-signals.js'),C=require('../static/signal-confidence.js');
const now=1787464801,SOURCE='BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2';
function data(){const q={source:SOURCE,bid:99,ask:100,time:now,received_at:now};q.bid=99.99;
 const c={version:E.VERSION,model_sha256:'a'.repeat(64),source:SOURCE,frame:'1h',strategy:'BREAKOUT_RETEST',name:'Breakout + Retest',direction:'LONG',state:'WATCH',score:100,
 statistical_status:'UNVALIDATED',probability_tp_before_sl:null,exchange_execution:false,manual_only:true,closed_at:1787464800,valid_until:1787468400,quote_time:now,quote_received_at:now,
 checks:[{passed:true,code:'TEST_CONDITION'}],rejection:[],name:'Breakout + Retest',entry_reason:'TEST',confirmation:'TEST',cancel:'TEST',score_basis:'TEST',indicators:{ema20:100,ema50:99,atr:3,rsi:50,macd:1,histogram:1},horizon:{min_seconds:3600,max_seconds:14400},stop_explanation:{anchor:92,reason:'TEST'},target_explanation:{reason:'TEST'},entry:100,sl:90,tp:130,net_rr:2,gross_rr:3,costs:{net_loss:12}};
 return {scope:'AURA6_PUBLIC_OBSERVER_ONLY',explanation_version:E.VERSION,execution_enabled:false,account_connected:false,observer:{running:true},server_time:now,fresh_frames:['1h'],quotes:{'1h':q},explainable_candidates:[c]};}
test('explainable WATCH requires actual strategy conditions, not a generic score',()=>{const d=data(),c=d.explainable_candidates[0];assert.equal(E.usable(d,c,now),true);
 for(const change of [x=>x.checks[0].passed=false,x=>x.state='CONFIRMED',x=>x.net_rr=1.49,x=>x.strategy='SCORE_ONLY',x=>x.rejection=['REJECT'],x=>x.probability_tp_before_sl=.8,x=>x.entry=101]){
 const x=structuredClone(c);change(x);assert.equal(E.usable(d,x,now),false);}
 assert.equal(E.position(c,24),2);assert.equal(E.position(c,0),null);assert.equal(E.position(c,NaN),null);
});
test('stale/source/quote/cutoff mismatch never exposes a fresh score or valid WATCH',()=>{for(const change of [d=>d.quotes['1h'].time-=6,d=>d.server_time-=11,d=>d.observer.running=false,d=>d.quotes['1h'].source='OTHER',d=>d.quotes['1h'].ask=99,d=>d.explainable_candidates[0].closed_at-=3600]){
 const d=data();change(d);assert.equal(E.fresh(d,d.explainable_candidates[0],now),false);assert.equal(E.usable(d,d.explainable_candidates[0],now),false);}
 const d=data();assert.equal(E.fresh(d,d.explainable_candidates[0],now+6),false);
});
test('new mode cannot qualify legacy generic-score WATCH',()=>{const d=data();assert.equal(C.usable(d,{state:'WATCH_RESEARCH'},now),false);});

test('malformed API candidates and incomplete explanations fail closed without exceptions',()=>{
 for(const value of [null,{},'bad',false,42,[null,{},'bad']]){const d={...data(),explainable_candidates:value};assert.doesNotThrow(()=>E.candidates(d).map(c=>E.fresh(d,c,now)));assert.equal(E.candidates(d).filter(c=>E.usable(d,c,now)).length,0);}
 for(const change of [c=>c.checks={},c=>c.checks=[null],c=>c.horizon=null,c=>c.indicators=null,c=>c.rejection='bad',c=>c.stop_explanation=null]){const d=data(),c=d.explainable_candidates[0];change(c);assert.equal(E.fresh(d,c,now),false);assert.equal(E.usable(d,c,now),false);}
});

test('quote refresh preserves card and open details; expiry removes the chart plan',()=>{
 const {readFileSync}=require('node:fs'),{runInNewContext}=require('node:vm');
 class Element {
  constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.events={};this.textContent='';this.hidden=false;this.open=false;}
  append(child){this.children.push(child);}
  replaceChildren(){this.children=[];}
  addEventListener(type,handler){this.events[type]=handler;}
 }
 const host=new Element('section'),events={},document={
  getElementById:id=>id==='aura-explainable'?host:null,
  createElement:tag=>new Element(tag),querySelector:()=>null,addEventListener:()=>{}
 };
 let time=now,render,overlays;
 const window={document,AuraSignalAlerts:{WebAudioPlayer:class{}},
  addEventListener:(type,handler)=>{events[type]=handler;},
  dispatchEvent:event=>{overlays=event.detail;}};
 const file=require.resolve('../static/explainable-signals.js');
 runInNewContext(readFileSync(file,'utf8'),{window,document,Date:class extends Date{static now(){return time*1000;}},
  CustomEvent:class{constructor(type,{detail}){this.detail=detail;}},setInterval:handler=>{render=handler;}});
 const d=data(),candidate=d.explainable_candidates[0],q=d.quotes['1h'];
 candidate.id='c'.repeat(64);
 const receive=()=>events['aura-preview-snapshot']({detail:d});
 receive();
 const cards=host.children.at(-1),card=cards.children.find(e=>e.dataset.frame==='1h'&&e.dataset.direction==='LONG');
 const details=card.children.find(e=>e.tag==='details'),body=details.children.at(-1),evidence=body.children[0];
 const button=card.children.find(e=>e.tag==='button');
 const plan=card.children.find(e=>e.tag==='section'),entry=plan.children[1].children[0].children[1];
 details.open=true;
 button.events.click();
 assert.equal(overlays['1h'].plan.entry,100);
 q.ask=candidate.entry=100.02;
 candidate.target_explanation.distance_atr=5.01;
 receive();
 assert.ok(cards.children.includes(card));
 assert.equal(card.dataset.scenarioId,candidate.id);
 assert.ok(details.open&&body.children.includes(evidence));
 assert.equal(entry.textContent,'100.02');
 time+=6;render();
 assert.equal(card.dataset.state,'UNKNOWN');
 assert.match(plan.children[0].textContent,/НЕАКТУАЛЕН/);
 assert.equal(entry.textContent,'100.02');
 assert.ok(button.hidden&&details.open);
 assert.equal(overlays['1h'],undefined);
});

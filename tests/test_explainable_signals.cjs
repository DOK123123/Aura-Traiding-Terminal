'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const E=require('../static/explainable-signals.js'),C=require('../static/signal-confidence.js');
const now=1787464801,SOURCE='BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2';
function data(){const q={source:SOURCE,bid:99,ask:100,time:now,received_at:now};q.bid=99.99;
 const c={version:E.VERSION,model_sha256:'a'.repeat(64),source:SOURCE,frame:'1h',strategy:'BREAKOUT_RETEST',name:'Breakout + Retest',direction:'LONG',state:'WATCH',score:100,
 statistical_status:'UNVALIDATED',probability_tp_before_sl:null,exchange_execution:false,manual_only:true,closed_at:1787464800,valid_until:1787468400,quote_time:now,quote_received_at:now,
 checks:[{passed:true}],rejection:[],entry:100,sl:90,tp:130,net_rr:2,gross_rr:3,costs:{net_loss:12}};
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

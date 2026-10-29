/* Replay decisions at recorded real receipt timestamps, not exchange timestamps.
 * Capture is made while observing public REST/WS and contains no future outcomes. */
'use strict';
const fs=require('node:fs'),crypto=require('node:crypto'),Feed=require('../static/manual-live-feed.js'),E=require('../static/manual-strategies.js'),{Observer}=require('../static/forward-observer.js');
(async()=>{
 const bytes=fs.readFileSync(process.argv[2]),records=JSON.parse(bytes),histories={},observer=new Observer(),states={},diagnostics={},events=[];let clock=0,live=0,quoteCount=0;
 const hub=new Feed.Hub({clock:()=>clock,fetcher:async url=>({ok:true,json:async()=>histories[({'1H':'1h','4H':'4h'})[new URL(url).searchParams.get('granularity')]||new URL(url).searchParams.get('granularity')]}),socket:()=>({readyState:1,send(){},close(){}}),timers:{setTimeout:()=>0,setInterval:()=>0,clearTimeout(){},clearInterval(){}},onData:s=>{
  if(s.status==='LIVE')live++;
  diagnostics[hub.diagnostic]=(diagnostics[hub.diagnostic]||0)+1;
  const rows=E.analyze(s,clock);for(const x of rows)states[x.state]=(states[x.state]||0)+1;
  observer.update(s,rows,clock);events.push({received_at:clock,status:s.status,quote_at:s.quote?.time,rows:rows.filter(x=>x.setup&&x.setup!=='WAIT')});
 }});
 for(const r of records){clock=r.received_at;if(r.kind==='history')histories[r.tf]=r.body;
  else if(r.kind==='start'){hub.running=true;await hub.connect();}
  else if(r.kind==='message'&&hub.ws?.onmessage){if(r.body.arg?.channel==='ticker'&&r.body.data)quoteCount++;hub.ws.onmessage({data:JSON.stringify(r.body)});}
 }
 fs.writeFileSync(process.argv[3],JSON.stringify({scope:'BOUNDED_REAL_PUBLIC_FORWARD_CAPTURE',source:'Bitget BTCUSDT USDT-M public REST/WS',capture_sha256:crypto.createHash('sha256').update(bytes).digest('hex'),first_received_at:records[0]?.received_at,last_received_at:clock,live_events:live,quote_events:quoteCount,decision_states:states,diagnostics,observations:observer.items,events,orders:0,edge:'UNVALIDATED',verdict:'INSUFFICIENT_EVIDENCE'},null,2));console.log(JSON.stringify({live_events:live,quote_events:quoteCount,observations:observer.items.length,orders:0}));
})().catch(e=>{console.error(e.message);process.exitCode=1;});

/* Offline synthetic scenarios only; no market event/Push delivery claims. */
const fs=require('fs'),http=require('http'),path=require('path'),assert=require('node:assert/strict');
const {chromium,devices}=require('playwright');const root=path.resolve(__dirname,'..');
let ticks=0,mode='WATCH',posts=0;
function snapshot(){const now=Date.now()/1000,id='a'.repeat(64),state=mode;const row={id,direction:'LONG',strategy:'TREND_PULLBACK',frame:'15m',status:state,score:70+ticks%30,detected_at:1700000000,refreshed_at:now,valid_until:now+60,revision:state==='WATCH'?2:3,initial:{confirmation:'SYNTHETIC FIXTURE ONLY',cancel:'STRUCTURAL_INVALIDATION'},missing:[],current_plan:state==='WATCH'?{entry:100,sl:95,tp:110,net_rr:1.7}:null,history:[{id:id+':1',at:1700000000,to:'CANDIDATE',reason:'MISSING_CONDITIONS'},{id:id+':2',at:1700000001,to:'WATCH',reason:'ALL_MANDATORY_CONDITIONS_MET',plan:{entry:100,sl:95,tp:110,net_rr:1.7}}]};
 const rows=[row];if(ticks>250)rows.unshift({...row,id:'b'.repeat(64),detected_at:1700000010,history:[{...row.history[0],id:'b'.repeat(64)+':1'}]});
 return {scope:'AURA5_SIGNAL_LOCK_V1',quotes:{'15m':{bid:100+ticks*.00001,ask:100.01+ticks*.00001,time:now,received_at:now}},storage:'SUPABASE',server_time:now,updated_at:now,error:null,records:rows,exchange_execution:false};}
const server=http.createServer((req,res)=>{if(req.method!=='GET'){posts++;res.writeHead(405).end();return;}
 if(req.url==='/'){res.setHeader('Content-Type','text/html');return res.end('<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:12px}select{max-width:100%}article{overflow-wrap:anywhere}pre{white-space:pre-wrap}</style><h1>LOCAL SYNTHETIC FIXTURE · NOT DEPLOYED</h1><button id="app-tab-signals">Сигналы</button><section id="aura-explainable"><p>Legacy fixture</p></section><script src="/static/signal-lock-ui.js"></script>');}
 if(req.url.startsWith('/api/preview/signals/locked')){ticks++;res.setHeader('Content-Type','application/json');return res.end(JSON.stringify(snapshot()));}
 if(req.url==='/static/signal-lock-ui.js'){res.setHeader('Content-Type','application/javascript');return res.end(fs.readFileSync(path.join(root,'static/signal-lock-ui.js')));}
 res.writeHead(404).end();});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));let b;try{b=await chromium.launch({...(process.env.CHROMIUM?{executablePath:process.env.CHROMIUM}:{}),args:['--no-sandbox']});const reports=[];
 for(const [name,device] of [['desktop',{}],['android412',{...devices['Pixel 7'],viewport:{width:412,height:915}}]]){ticks=0;mode='WATCH';const c=await b.newContext(device),p=await c.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.addInitScript(()=>{const timer=window.setTimeout.bind(window);window.setTimeout=(fn,ms,...args)=>timer(fn,ms===1500?3:ms,...args);});
 await p.goto('http://127.0.0.1:'+server.address().port);await p.waitForSelector('.server-lock [data-state="WATCH"]');
 const card=p.locator('.server-lock article[data-side="LONG"]');await card.locator('details > summary').click();const before=await card.getAttribute('data-scenario-id');
 await p.evaluate(()=>scrollTo(0,100));const y=await p.evaluate(()=>scrollY);
 await p.waitForFunction(()=>document.querySelector('.server-lock select').options.length===2,{},{timeout:30000});
 while(ticks<510)await p.waitForTimeout(20);
 assert.equal(await card.getAttribute('data-scenario-id'),before);assert.equal(await card.locator('details').getAttribute('open'),'');assert.equal(await p.evaluate(()=>scrollY),y);
 assert.match(await card.innerText(),/Entry 100.*SL 95/);assert.match(await p.locator('.server-lock [role="status"]').innerText(),/Новых событий/);
 mode='UNKNOWN';await p.waitForFunction(()=>document.querySelector('.server-lock article').dataset.state==='UNKNOWN');assert.doesNotMatch(await card.locator('p').allTextContents().then(x=>x.join(' ')),/Entry 100/);
 assert.equal(await card.getAttribute('data-scenario-id'),before);
 await card.locator('select').selectOption('b'.repeat(64));assert.equal(await card.getAttribute('data-scenario-id'),'b'.repeat(64));
 assert.equal(posts,0);assert.deepEqual(errors,[]);reports.push({name,quoteUpdates:ticks,stableSelection:true,detailsPreserved:true,scrollPreserved:true,unknownHidesPlan:true,manualSelection:true,posts,errors});await c.close();}
 console.log(JSON.stringify({status:'PASS',mode:'OFFLINE_SYNTHETIC_FIXTURE',reports}));
 }finally{await b?.close();server.close();}})().catch(e=>{console.error(e);process.exitCode=1;});

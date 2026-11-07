/* Actual Preview HTML + controlled HTTP fixtures. No hosted market/Push claims. */
const fs=require('fs'),http=require('http'),path=require('path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {chromium,devices}=require('playwright');const root=path.resolve(__dirname,'..');
const html=require('child_process').execFileSync(process.env.PYTHON||'.venv/bin/python',['-c',"from app.manual_preview.page import page;print(page('DUMMY_LOCAL_TOKEN',server_signals=True,server_lock=True))"],{cwd:root,encoding:'utf8'});
let ticks=0,mode='WATCH',posts=0,pushReady=false;const boot=Date.now()/1000,FRAMES=['5m','15m','1h','4h'];
const identity=(frame,side,next=false)=>frame==='15m'&&side==='LONG'&&!next?'a'.repeat(64):crypto.createHash('sha256').update(frame+side+(next?'NEW_STRUCTURE':'')).digest('hex');
function makeRow(frame,side,now,next=false){const id=identity(frame,side,next),watch=mode==='WATCH'||next;
 const checks=['EMA_TREND','TREND_STRUCTURE','PULLBACK','RSI','CLOSED_CANDLE_CONFIRMATION'].map(code=>({code,passed:true,weight:1,points:20,max_points:20,actual:1,required:'SYNTHETIC TEST CONDITION'}));
 const initial={confirmation:'SYNTHETIC FIXTURE ONLY',cancel:'STRUCTURAL_INVALIDATION',checks:checks.map((x,i)=>({...x,passed:i!==0})),score:80};
 const plan=side==='LONG'?{entry:100,sl:95,tp:110,net_rr:1.7}:{entry:100,sl:105,tp:90,net_rr:1.7};
 return {id,direction:side,strategy:frame==='15m'?'TREND_PULLBACK':'BREAKOUT_RETEST',frame,status:watch?'WATCH':'UNKNOWN',score:100,detected_at:boot+(next?1:frame==='15m'?0:-1),refreshed_at:now,valid_until:boot+3600,revision:watch?2:3,initial,current_checks:checks,last_evaluated_at:now,last_confirmed_at:now,missing:[],current_plan:watch?plan:null,history:[{id:id+':1',at:boot,to:'CANDIDATE',reason:'MISSING_MANDATORY_CONDITIONS'},{id:id+':2',at:boot+.1,to:'WATCH',reason:'ALL_MANDATORY_CONDITIONS_MET',plan}]};}
function snapshot(){const now=Date.now()/1000,rows=FRAMES.flatMap(frame=>['LONG','SHORT'].map(side=>makeRow(frame,side,now)));
 if(ticks>250)rows.unshift({...makeRow('15m','LONG',now),id:'b'.repeat(64),status:'UNKNOWN',detected_at:boot-86400,current_plan:null,history:[{id:'b'.repeat(64)+':1',at:boot-86400,to:'UNKNOWN',reason:'UNTRUSTED_OR_STALE_DATA'}]});
 if(mode==='RECOVERED')rows.unshift(...FRAMES.flatMap(frame=>['LONG','SHORT'].map(side=>makeRow(frame,side,now,true))));
 const market_regimes=Object.fromEntries(FRAMES.map((f,i)=>[f,{state:['TREND_UP','TRANSITION','RANGE','TREND_DOWN'][i],closed_at:Math.floor(now/({ '5m':300,'15m':900,'1h':3600,'4h':14400}[f]))*({'5m':300,'15m':900,'1h':3600,'4h':14400}[f]),metrics:{adx14:i===2?10:i===1?22:30,atr14:2,ema_slope_atr_per_bar:i===2?0:i===3?-.2:.2,structure:i===2?'MIXED_OR_EQUAL':i===3?'LH_LL':'HH_HL',range_low:90,range_high:110}}]));
 return {scope:'AURA5_SIGNAL_LOCK_V1',quotes:Object.fromEntries(FRAMES.map(f=>[f,{bid:100+ticks*.00001,ask:100.01+ticks*.00001,time:now,received_at:now}])),market_regimes,storage:'SUPABASE',server_time:now,updated_at:now,error:null,records:rows,exchange_execution:false};}
const server=http.createServer((req,res)=>{if(req.method!=='GET'){posts++;res.writeHead(405).end();return;}
 if(req.url==='/'){res.setHeader('Content-Type','text/html');return res.end(html);}
 if(req.url.startsWith('/api/preview/signals/locked')){ticks++;res.setHeader('Content-Type','application/json');return res.end(JSON.stringify(snapshot()));}
 if(req.url==='/api/preview/push/config'){res.setHeader('Content-Type','application/json');return res.end(JSON.stringify({ready:pushReady,code:pushReady?null:'VAPID_NOT_CONFIGURED',public_key:'DUMMY_NOT_USED_WHEN_DENIED'}));}
 if(req.url==='/aura5-sw.js'){res.setHeader('Content-Type','application/javascript');res.setHeader('Service-Worker-Allowed','/');return res.end(fs.readFileSync(path.join(root,'static/aura5-sw.js')));}
 if(req.url.startsWith('/static/')){const file=path.resolve(root,'.'+req.url.split('?')[0]);if(file.startsWith(root+'/static/')&&fs.existsSync(file)){res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'image/svg+xml');return res.end(fs.readFileSync(file));}}
 res.writeHead(404).end();});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;try{browser=await chromium.launch({...(process.env.CHROMIUM?{executablePath:process.env.CHROMIUM}:{}),args:['--no-sandbox']});const reports=[];
 for(const [name,device] of [['desktop',{}],['android412',{...devices['Pixel 7'],viewport:{width:412,height:915}}]]){ticks=0;mode='WATCH';pushReady=false;const context=await browser.newContext(device),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{window.WebSocket=class{constructor(){this.readyState=1;}send(){}close(){}};const timer=window.setTimeout.bind(window);window.setTimeout=(fn,ms,...args)=>timer(fn,ms===1500?3:ms,...args);});
 await page.goto('http://127.0.0.1:'+server.address().port);await page.locator('#app-tab-signals').click();await page.waitForSelector('.server-lock [data-state="WATCH"]');
 const card=side=>page.locator('.server-lock article[data-side="'+side+'"]');
 for(const frame of FRAMES)for(const side of ['LONG','SHORT']){await card(side).locator('select').selectOption(identity(frame,side));assert.equal(await card(side).getAttribute('data-scenario-id'),identity(frame,side));assert.match(await card(side).locator('h3').innerText(),new RegExp(frame));}
 const long=card('LONG');await long.locator('select').selectOption(identity('15m','LONG'));await long.locator('details > summary').click();
 assert.match(await long.innerText(),/5 из 5/);assert.match(await long.innerText(),/вклад 20 из 20/);
 const handle=await long.elementHandle(),before=await long.getAttribute('data-scenario-id');const cardTop=await long.evaluate(e=>e.getBoundingClientRect().top+scrollY);
 await page.evaluate(()=>scrollTo(0,100));const y=await page.evaluate(()=>scrollY);
 while(ticks<510)await page.waitForTimeout(20);
 assert.equal(await handle.evaluate(e=>e===document.querySelector('.server-lock article[data-side="LONG"]')),true);
 assert.equal(await long.getAttribute('data-scenario-id'),before);assert.equal(await long.locator('details').getAttribute('open'),'');assert.equal(await page.evaluate(()=>scrollY),y);assert.equal(await long.evaluate(e=>e.getBoundingClientRect().top+scrollY),cardTop);
 assert.match(await long.innerText(),/Entry 100.*SL 95/);assert.match(await page.locator('.server-lock [role="status"]').innerText(),/Новых событий/);
 assert.equal(await long.locator('select').inputValue(),before);assert.notEqual(before,'b'.repeat(64));
 mode='UNKNOWN';await page.waitForFunction(()=>document.querySelector('.server-lock article').dataset.state==='NONE');assert.doesNotMatch(await long.innerText(),/Entry 100/);
 await long.locator('select').selectOption('b'.repeat(64));assert.equal(await long.getAttribute('data-pinned'),'true');assert.match(await long.innerText(),/Исторический балл/);
 await page.reload();await page.locator('#app-tab-signals').click();await page.waitForFunction(()=>document.querySelector('.server-lock article').dataset.scenarioId==='b'.repeat(64));assert.equal(await long.locator('details').getAttribute('open'),'');
 mode='RECOVERED';await page.waitForFunction(id=>[...document.querySelectorAll('.server-lock select option')].some(o=>o.value===id),identity('15m','LONG',true));assert.equal(await long.getAttribute('data-scenario-id'),'b'.repeat(64));
 await long.getByRole('button',{name:'Открепить чтение',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.server-lock article').dataset.state==='WATCH');assert.notEqual(await long.getAttribute('data-scenario-id'),before);
 assert.equal(await long.locator('details').getAttribute('open'),'');assert.equal(await page.locator('.market-regimes > p').count(),4);
 await page.locator('.push-settings > summary').click();await page.getByRole('button',{name:'Включить Push',exact:true}).click();assert.match(await page.locator('.push-settings p').innerText(),/VAPID не настроен/);
 const scope=await page.evaluate(async()=>{const reg=await navigator.serviceWorker.register('/aura5-sw.js',{scope:'/'});await navigator.serviceWorker.ready;return reg.scope;});assert.ok(scope.endsWith('/'));
 pushReady=true;await page.reload();await page.locator('#app-tab-signals').click();await page.locator('.push-settings > summary').click();await page.getByRole('button',{name:'Включить Push',exact:true}).click();await page.waitForFunction(()=>/запрещены|не получено/.test(document.querySelector('.push-settings p').textContent));
 assert.equal(posts,0);assert.deepEqual(errors,[]);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));const out=path.resolve(process.argv[2]||'work/signal-lock-browser');fs.mkdirSync(out,{recursive:true});await page.evaluate(()=>{const p=document.createElement('p');p.textContent='LOCAL OFFLINE SYNTHETIC REGRESSION · NOT HOSTED LIVE';document.body.prepend(p);});await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});await long.screenshot({path:path.join(out,name+'-long.png')});
 reports.push({name,quoteUpdates:ticks,allFramesBothSides:true,currentEvidenceNotInitial:true,stableCard:true,detailsPreserved:true,scrollPreserved:true,terminalMovedToHistory:true,manualHistoryPinAndReload:true,newStructureAfterRecovery:true,marketRegimes:4,serviceWorkerRegistered:true,missingVapidHandled:true,permissionDeniedHandled:true,posts,errors});await context.close();}
 const result={status:'PASS',mode:'OFFLINE_SYNTHETIC_FIXTURE',reports};const out=path.resolve(process.argv[2]||'work/signal-lock-browser');fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser?.close();server.close();}})().catch(e=>{console.error(e);process.exitCode=1;});

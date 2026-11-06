/* Actual Preview HTML and SW, synthetic fixtures; never real Android delivery. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');const {chromium,devices}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.argv[2]||'work/signal-lock-integration-browser');fs.mkdirSync(out,{recursive:true});
const html=execFileSync(process.env.PYTHON||'python',['-c','from app.manual_preview.page import page; print(page("DUMMY_BROWSER_PUSH_CSRF_ONLY",server_signals=True,signal_lock=True))'],{cwd:root,encoding:'utf8'});
let mode='CANDIDATE',withNew=false,nonGet=[];const id='a'.repeat(64),newId='b'.repeat(64),detected=Date.now()/1000-20;
const plan={entry:60000.1,sl:59700,tp:60900,net_rr:2.1,risk_usdt_per_btc:450};
function snapshot(){
 const now=Date.now()/1000,q={source:'BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2',bid:59999.9,ask:60000.1,last:60000,time:now,received_at:now};
 const event={id,direction:'LONG',frame:'15m',strategy:'TREND_PULLBACK',status:mode,detected_at:detected,last_seen:now,
  valid_until:mode==='EXPIRED'?now-1:detected+900,initial_score:70,score:mode==='WATCH'?100:75,
  missing:['RSI'],reasons:['RSI'],check_details:[{code:'RSI',passed:false}],plan:mode==='WATCH'?plan:null,
  archive_plan:['WATCH','UNKNOWN','EXPIRED','INVALIDATED'].includes(mode)?plan:null,execution_enabled:false};
 const events=withNew?[{...event,id:newId,direction:'SHORT',detected_at:detected+1,plan:null,status:'CANDIDATE'},event]:[event];
 return {scope:'AURA6_PUBLIC_OBSERVER_ONLY',execution_enabled:false,account_connected:false,explanation_version:'AURA5_EXPLAINABLE_V1',
  observer:{running:true,cycles:4,frame_errors:{}},server_time:now,fresh_frames:['15m'],quotes:{'15m':q},
  explainable_candidates:[],confidence_candidates:[],records:[],alerts:[],watch_alerts:[],
  signal_lock:{enabled:true,ready:mode!=='UNKNOWN',events,quote:q,execution_enabled:false}};
}
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost'),p=url.pathname;
 if(req.method!=='GET'){nonGet.push(p);res.writeHead(405).end();return;}
 if(p==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);return;}
 if(p==='/api/preview/signals/snapshot'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(snapshot()));return;}
 if(p==='/api/preview/push/status'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({enabled:true,configured:false,real_android_delivery:'UNKNOWN'}));return;}
 if(p.startsWith('/api/preview/lock/event/')){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({...snapshot().signal_lock.events.find(e=>e.id===p.split('/').pop()),archived:true,plan:null}));return;}
 if(p==='/api/preview/lock/history'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({events:[],next_before:null}));return;}
 if(p.startsWith('/api/')){res.writeHead(503,{'Content-Type':'application/json'}).end('{}');return;}
 const file=p==='/signal-lock-sw.js'?path.join(root,'static/signal-lock-sw.js'):path.resolve(root,'.'+p);
 if(!file.startsWith(root+'/static/')||!fs.existsSync(file)){res.writeHead(404).end();return;}
 res.setHeader('Content-Type',(file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'image/svg+xml')+'; charset=utf-8');
 if(p==='/signal-lock-sw.js')res.setHeader('Service-Worker-Allowed','/');res.end(fs.readFileSync(file));
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const url='http://127.0.0.1:'+server.address().port;let browser;const reports=[];
 try{
  browser=await chromium.launch({headless:true});
  for(const [name,opts] of [['desktop',{viewport:{width:1280,height:900}}],['poco-432',{...devices['Pixel 7'],viewport:{width:432,height:960}}],['android-360',{...devices['Pixel 7'],viewport:{width:360,height:800}}]]){
   mode='CANDIDATE';withNew=false;const context=await browser.newContext(opts),page=await context.newPage(),errors=[];
   await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
   await page.addInitScript(()=>{window.WebSocket=class{constructor(){this.readyState=1;}send(){}close(){this.readyState=3;}};});
   page.on('pageerror',e=>errors.push(e.message));await page.goto(url+'/#app-signals');
   const card=page.locator('#aura-signal-lock article');await card.locator('[data-heading]').filter({hasText:'LONG'}).waitFor();
   assert.equal(await page.locator('[role="tab"]').count(),4);
   await card.locator('summary').click();await page.evaluate(()=>scrollTo(0,160));
   const before=await page.evaluate(()=>scrollY);withNew=true;
   const data=snapshot();
   await page.evaluate(payload=>{for(let i=0;i<500;i++){
    const p=structuredClone(payload),now=Date.now()/1000;
    p.signal_lock.events.forEach(e=>{e.last_seen=now;e.score=[70,75,80][i%3];});
    p.signal_lock.quote.last=60000+i/100;window.dispatchEvent(new CustomEvent('aura-preview-snapshot',{detail:p}));
   }},data);
   assert.match(await card.locator('[data-heading]').textContent(),/LONG/);
   assert.equal(await card.locator('details').evaluate(e=>e.open),true);assert.equal(await page.evaluate(()=>scrollY),before);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   mode='WATCH';await page.evaluate(p=>dispatchEvent(new CustomEvent('aura-preview-snapshot',{detail:p})),snapshot());
   assert.equal(await card.locator('[data-plan]').isVisible(),true);
   for(const state of ['UNKNOWN','EXPIRED','INVALIDATED']){
    mode=state;await page.evaluate(p=>dispatchEvent(new CustomEvent('aura-preview-snapshot',{detail:p})),snapshot());
    assert.equal(await card.locator('[data-plan]').isVisible(),false);
    assert.match(await card.locator('[data-archive]').textContent(),/Архив первого WATCH/);
   }
   mode='CANDIDATE';await page.evaluate(p=>dispatchEvent(new CustomEvent('aura-preview-snapshot',{detail:p})),snapshot());
   await page.locator('#app-tab-more').click();assert.equal(await page.locator('#app-more [data-history-root]').isVisible(),true);
   await page.locator('#app-more [data-history] button').filter({hasText:'SHORT'}).click();
   assert.equal(await page.locator('#app-signals').isVisible(),true);assert.match(await card.locator('[data-heading]').textContent(),/SHORT/);
   await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});
   await page.goto(url+'/?signal_event='+id+'#app-signals');await page.locator('#aura-signal-lock [data-heading]').filter({hasText:'LONG'}).waitFor();
   // Actual Service Worker registration and real PushEvent dispatch through CDP.
   // There is no FCM subscription or network delivery in this test.
   await context.grantPermissions(['notifications'],{origin:url});
   const cdp=await context.newCDPSession(page);let registrationId;
   cdp.on('ServiceWorker.workerRegistrationUpdated',e=>{const r=e.registrations.find(r=>r.scopeURL===url+'/');if(r)registrationId=r.registrationId;});
   await cdp.send('ServiceWorker.enable');
   await page.evaluate(async()=>{await navigator.serviceWorker.register('/signal-lock-sw.js',{scope:'/'});await navigator.serviceWorker.ready;});
   for(let i=0;i<30&&!registrationId;i++)await new Promise(r=>setTimeout(r,100));
   assert.ok(registrationId,'Actual service worker registration missing');
   const push={event_id:id,direction:'LONG',frame:'15m',status:'WATCH',score:100,at:Date.now()/1000,expires_at:Date.now()/1000+60};
   await cdp.send('ServiceWorker.deliverPushMessage',{origin:url,registrationId,data:JSON.stringify(push)});
   await page.waitForFunction(async()=>{const r=await navigator.serviceWorker.ready;return (await r.getNotifications()).some(n=>n.data?.event_id==='a'.repeat(64));});
   const notice=await page.evaluate(async()=>{const list=await(await navigator.serviceWorker.ready).getNotifications();return list.map(n=>({title:n.title,tag:n.tag,body:n.body}));});
   assert.match(notice[0].body,/не вероятность прибыли/);
   assert.deepEqual(errors,[]);reports.push({name,updates:500,selectedStable:true,scroll:true,history:true,lifecycle:true,workerRegistered:true,syntheticPush:true,realAndroidDelivery:'UNKNOWN',errors});
   await context.close();
  }
  assert.deepEqual(nonGet,[]);fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify({reports,nonGetRequests:nonGet.length,realAndroidDelivery:'UNKNOWN'},null,2));console.log(JSON.stringify({reports,posts:nonGet.length}));
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(error=>{console.error(error);process.exitCode=1;});

/* Offline UI component fixture; never registers a real subscription or order. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),http=require('node:http'),path=require('node:path');
const {chromium,devices}=require('playwright');
(async()=>{
 const out=process.argv[2]||'work/signal-lock-browser';fs.mkdirSync(out,{recursive:true});
 const allowed={'/signal-lock.js':'static/signal-lock.js','/signal-lock.css':'static/signal-lock.css'};
 const server=http.createServer((req,res)=>{
  if(req.method!=='GET'){res.writeHead(405);res.end();return;}
  if(allowed[req.url]){res.setHeader('Content-Type',(req.url.endsWith('.js')?'text/javascript':'text/css')+'; charset=utf-8');res.end(fs.readFileSync(allowed[req.url]));return;}
  if(req.url!=='/'){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type','text/html; charset=utf-8');res.end('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/signal-lock.css"><div id="view"></div><script src="/signal-lock.js"></script><script>window.clock=1000;window.view=AuraSignalLock.mount(document.getElementById("view"),{now:()=>clock});</script>');
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 let browser;const results=[];
 try{
  browser=await chromium.launch({headless:true});
  for(const [label,options] of [['desktop',{viewport:{width:1280,height:900}}],['poco-432',{...devices['Pixel 7'],viewport:{width:432,height:960}}],['android-360',{...devices['Pixel 7'],viewport:{width:360,height:800}}]]){
   const context=await browser.newContext(options),page=await context.newPage(),errors=[],posts=[];
   page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()!=='GET')posts.push(r.method());});
   await page.goto('http://127.0.0.1:'+server.address().port);
   await page.evaluate(()=>{
    window.old={id:'a'.repeat(64),frame:'15m',direction:'LONG',strategy:'TREND_PULLBACK',status:'CANDIDATE',score:70,detected_at:900,valid_until:3000,last_seen:1000,plan:null,missing:['X','Y']};view.update([old]);
   });
   await page.locator('summary').click();
   assert.equal(await page.locator('[data-status]').textContent(),'Предварительный кандидат');
   assert.match(await page.locator('summary').textContent(),/Открыть подробности/);
   const original=await page.evaluate(()=>view.selection());
   await page.evaluate(()=>window.scrollTo(0,150));
   const before=await page.evaluate(()=>scrollY);
   await page.evaluate(()=>{
    for(let i=0;i<500;i++){
     clock=1000+i;const row={...old,last_seen:clock,score:[70,75,80][i%3]};
     view.quote((60000+i/100).toFixed(2)+' · LIVE');
     view.update([{...row,id:'b'.repeat(64),direction:'SHORT',detected_at:1001},row]);
    }
   });
   assert.equal(await page.evaluate(()=>view.selection()),original);
   assert.equal(await page.locator('details').evaluate(e=>e.open),true);
   assert.equal(await page.evaluate(()=>scrollY),before);
   assert.match(await page.locator('[data-heading]').textContent(),/LONG/);
   assert.equal(await page.locator('[data-plan]').isVisible(),false);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   await page.screenshot({path:path.join(out,label+'.png'),fullPage:true});
   await page.locator('[data-frame="1h"]').click();
   await page.reload();
   assert.equal(await page.evaluate(()=>view.frame()),'1h');
   assert.equal(await page.locator('details').evaluate(e=>e.open),true);
   await page.locator('[data-frame="15m"]').click();
   assert.equal(await page.evaluate(()=>view.selection()),original);
   await page.evaluate(()=>{view.update([{...window.old,id:'a'.repeat(64),frame:'15m',status:'WATCH',last_seen:1000,valid_until:3000,detected_at:900,plan:{entry:100}}]);clock=1006;view.tick();});
   assert.equal(await page.locator('[data-plan]').isVisible(),false);
   assert.deepEqual(errors,[]);assert.deepEqual(posts,[]);
   results.push({viewport:label,quotes:500,selection:'PASS',scroll:'PASS',overflow:false,nonGetRequests:posts.length,errors:errors.length});
   await context.close();
  }
  fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify({scope:'OFFLINE_COMPONENT_ONLY',realAndroidDelivery:'NOT_TESTED',results},null,2));
  console.log(JSON.stringify(results));
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});

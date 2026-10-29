/* Offline UI integration: real saved Bitget OHLC for replay, clearly modeled event
 * transport for notification tests. Real Web Audio nodes (not a mocked player). */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process'),{chromium,devices}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.argv[2]||'work/replay-alerts-browser');process.chdir(root);fs.mkdirSync(out,{recursive:true});
const py=process.env.PYTHON||'python',html=execFileSync(py,['-c','from app.manual_preview.page import page; print(page("DUMMY_ONLY_BROWSER_TOKEN"))'],{encoding:'utf8'});
const payloads=JSON.parse(execFileSync(py,['-c','import json,time; from app.manual_preview.history import archive_history; print(json.dumps({tf:archive_history(tf,1790812800,1793232000,time.time()) for tf in ("15m","1h","4h")}))'],{encoding:'utf8',maxBuffer:5e6}));
const R=require('../static/historical-replay.js'),proof=new R.Replay(payloads['15m']);while(!proof.done)proof.next();const long=proof.journal.find(x=>x.state==='LONG'),short=proof.journal.find(x=>x.state==='SHORT');assert.ok(long&&short);
let posts=0,historyLoads=0;
const server=http.createServer((req,res)=>{
 if(req.method!=='GET'){posts++;res.writeHead(405).end();return;}
 if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end(html);return;}
 if(req.url.startsWith('/api/preview/bitget/history?')){historyLoads++;const q=new URL(req.url,'http://localhost').searchParams,p=payloads[q.get('timeframe')];if(!p||Number(q.get('start'))!==p.start||Number(q.get('end'))!==p.end){res.writeHead(400).end('{}');return;}const reply=()=>{if(res.destroyed)return;res.setHeader('Content-Type','application/json');res.end(JSON.stringify(p));};if(q.get('source')==='bitget')setTimeout(reply,300);else reply();return;}
 if(req.url.startsWith('/api/')){res.writeHead(503,{'Content-Type':'application/json'}).end('{}');return;}
 const file=path.resolve(root,'.'+req.url.split('?')[0]);if(!file.startsWith(root+'/static/')||!fs.existsSync(file)){res.writeHead(404).end();return;}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'image/svg+xml');res.end(fs.readFileSync(file));
});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser,activePage;const results=[];
try{
 browser=await chromium.launch({...(process.env.CHROMIUM?{executablePath:process.env.CHROMIUM}:{}),args:['--no-sandbox']});
 for(const mobile of [false,true]){
  const context=await browser.newContext(mobile?devices['Pixel 7']:{});await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();activePage=page;const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{window.__now=1790871300;Date.now=()=>window.__now*1000;window.__heartbeat=0;setInterval(()=>window.__heartbeat++,10);window.__frequencies=[];
   const C=window.AudioContext||window.webkitAudioContext;if(C){const original=C.prototype.createOscillator;C.prototype.createOscillator=function(...args){const o=original.apply(this,args),start=o.start.bind(o);o.start=(...a)=>{window.__frequencies.push(o.frequency.value);return start(...a);};return o;};}
  });
  await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>window.AuraReplayUI&&window.AuraLiveAlerts);
  assert.equal(await page.evaluate(()=>AuraLiveAlerts.player.context),null);
  await page.locator('#sa-enabled').check();await page.waitForFunction(()=>AuraLiveAlerts.alerts.ready&&AuraLiveAlerts.player.context.state==='running');
  const emit=async (row,live=true)=>page.evaluate(({row,live})=>{window.__now=row.formed_at;window.dispatchEvent(new CustomEvent('aura-manual-signals',{detail:{rows:[row],now:row.formed_at,snapshot:{status:live?'LIVE':'STALE'}}}));},{row,live});
  const liveRow=(sample,at=sample.formed_at)=>({...sample,mode:undefined,fresh:true,formed_at:at,valid_until:at+900,id:[sample.version,sample.strategy,900,at].join(':')});
  await emit(liveRow(long));await page.waitForFunction(()=>AuraLiveAlerts.player.plays===1);assert.deepEqual(await page.evaluate(()=>__frequencies),[660,880]);
  for(let i=0;i<4;i++)await emit(liveRow(long));assert.equal(await page.evaluate(()=>AuraLiveAlerts.player.plays),1);
  for(const bad of [{...liveRow(short),state:'WAIT'},{...liveRow(short),state:'REJECTED'},{...liveRow(short),fresh:false},{...liveRow(short),entry:null},{...liveRow(short),mode:'HISTORICAL_REPLAY'}])await emit(bad);
  await emit(liveRow(short),false);assert.equal(await page.evaluate(()=>AuraLiveAlerts.player.plays),1);
  await page.locator('#sa-long').uncheck();const muted=liveRow(long,long.formed_at+900);await emit(muted);await page.locator('#sa-long').check();await emit(muted);assert.equal(await page.evaluate(()=>AuraLiveAlerts.player.plays),1);
  await page.locator('#sa-volume').evaluate(el=>{el.value='0.55';el.dispatchEvent(new Event('input'));});
  await emit(liveRow(short));await page.waitForFunction(()=>AuraLiveAlerts.player.plays===2);assert.deepEqual((await page.evaluate(()=>__frequencies)).slice(-2),[440,330]);
  await page.locator('#sa-enabled').uncheck();await emit(liveRow(short,short.formed_at+900));assert.equal(await page.evaluate(()=>AuraLiveAlerts.player.plays),2);
  await page.locator('#sa-test').click();await page.waitForFunction(()=>AuraLiveAlerts.player.plays===3);
  await page.locator('#sa-enabled').check();await page.reload();await page.waitForFunction(()=>window.AuraLiveAlerts&&window.AuraReplayUI);
  assert.equal(await page.locator('#sa-enabled').isChecked(),true);assert.equal(await page.locator('#sa-volume').inputValue(),'0.55');assert.equal(await page.evaluate(()=>AuraLiveAlerts.alerts.ready),false);
  await page.locator('#sa-arm').click();await page.waitForFunction(()=>AuraLiveAlerts.alerts.ready);await emit(liveRow(short,short.formed_at+900));assert.equal(await page.evaluate(()=>AuraLiveAlerts.player.plays),0);
  await emit(liveRow(short,short.formed_at+1800));await page.waitForFunction(()=>AuraLiveAlerts.player.plays===1);
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{value:true,configurable:true});document.dispatchEvent(new Event('visibilitychange'));});assert.equal(await page.evaluate(()=>AuraLiveAlerts.alerts.ready),false);
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{value:false,configurable:true});document.dispatchEvent(new Event('visibilitychange'));});await page.locator('#sa-arm').click();await page.waitForFunction(()=>AuraLiveAlerts.alerts.ready);
  const playsBefore=await page.evaluate(()=>AuraLiveAlerts.player.plays);
  await page.locator('#aura-replay-panel > summary').click();await page.locator('#rp-load').click();await page.waitForFunction(()=>AuraReplayUI.model?.total===2688);
  const initial=await page.evaluate(()=>AuraReplayUI.model.counts.processed);await page.locator('#rp-next').click();assert.equal(await page.evaluate(()=>AuraReplayUI.model.counts.processed),initial+1);
  for(const speed of ['1','10','50','100','max']){await page.locator('#rp-speed').selectOption(speed);const before=await page.evaluate(()=>AuraReplayUI.model.counts.processed);await page.locator('#rp-play').click();await page.waitForFunction(n=>AuraReplayUI.model.counts.processed>n,before);await page.locator('#rp-pause').click();assert.equal(await page.evaluate(()=>AuraReplayUI.running),false);}
  await page.locator('#rp-reset').click();assert.equal(await page.evaluate(()=>AuraReplayUI.model.counts.processed),0);
  for(let i=0;i<20;i++){await page.locator('#rp-signal').click();await page.waitForFunction(()=>!AuraReplayUI.running);if(await page.evaluate(()=>AuraReplayUI.model.counts.SHORT>0&&AuraReplayUI.model.counts.LONG>0))break;}
  assert.ok(await page.evaluate(()=>AuraReplayUI.model.counts.SHORT>0&&AuraReplayUI.model.counts.LONG>0));
  assert.match(await page.locator('#rp-plan').textContent(),/Entry .*SL .*TP .*R\/R/);await page.waitForFunction(()=>AuraReplayUI.levels.length===3&&AuraReplayUI.levels.every(x=>x.y!==null&&x.y>=0&&x.y<=document.getElementById('rp-chart').clientHeight));assert.equal(await page.evaluate(()=>AuraLiveAlerts.player.plays),playsBefore);
  const downloadPromise=page.waitForEvent('download');await page.locator('#rp-csv').click();const download=await downloadPromise;await download.saveAs(path.join(out,mobile?'mobile.csv':'desktop.csv'));assert.match(fs.readFileSync(path.join(out,mobile?'mobile.csv':'desktop.csv'),'utf8'),/REJECTED/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  if(mobile){await page.locator('#rp-chart').scrollIntoViewIfNeeded();const b=await page.locator('#rp-chart').boundingBox();await page.touchscreen.tap(b.x+b.width/2,b.y+b.height/2);const cdp=await context.newCDPSession(page);await cdp.send('Input.synthesizePinchGesture',{x:b.x+b.width/2,y:b.y+b.height/2,scaleFactor:1.2,gestureSourceType:'touch'});}
  await page.screenshot({path:path.join(out,mobile?'mobile.png':'desktop.png'),fullPage:true});
  const count=await page.evaluate(()=>AuraReplayUI.model.counts);await page.locator('#rp-source').selectOption('bitget');await page.locator('#rp-load').click();await page.locator('#rp-reset').click();assert.match(await page.locator('#rp-status').textContent(),/Сброшено/);await page.locator('#rp-load').click();await page.waitForFunction(()=>document.getElementById('rp-status').textContent.includes('не совпал'));assert.equal(await page.evaluate(()=>AuraReplayUI.model),null);assert.deepEqual(errors,[]);results.push({mobile,audioContext:'REAL_WEB_AUDIO_RUNNING_AFTER_GESTURE',longFrequencies:[660,880],shortFrequencies:[440,330],masterMute:true,longMute:true,settingsReload:true,noDuplicateAfterReload:true,hiddenRearm:true,replaySilent:true,speeds:[1,10,50,100,'max'],autoPause:true,nextCandle:true,nextSignal:true,csv:true,resetCancelsLoad:true,sourceMismatchRejected:true,allThreeLevelsVisible:true,count,errors});await context.close();
 }
 assert.equal(posts,0);fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({status:'PASS',scope:'OFFLINE_BROWSER_REAL_ARCHIVE_MODELED_NOTIFICATION_TRANSPORT',physical_android:false,human_audibility:'NOT_VERIFIED',posts,historyLoads,real_replay_counts:proof.counts,results},null,2));console.log(JSON.stringify({status:'PASS',posts,historyLoads,results}));
}catch(e){if(activePage&&!activePage.isClosed()){fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify(await activePage.evaluate(()=>({replay:document.getElementById('rp-status')?.textContent,counts:window.AuraReplayUI?.model?.counts,audio:document.getElementById('sa-status')?.textContent,audioReady:window.AuraLiveAlerts?.alerts.ready,plays:window.AuraLiveAlerts?.player.plays})),null,2));await activePage.screenshot({path:path.join(out,'failure.png'),fullPage:true});}throw e;}
finally{await browser?.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});

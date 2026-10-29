/* Local-only Chromium desktop / Android touch emulation. Real historical OHLC,
 * modeled quotes, offline API; never evidence of current LIVE or forward profit. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),zlib=require('node:zlib'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process'),{chromium,devices}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.argv[2]||'work/manual-strategies-browser');process.chdir(root);fs.mkdirSync(out,{recursive:true});
const html=execFileSync(process.env.PYTHON||'python',['-c','from app.manual_preview.page import page; print(page("DUMMY_TEST_TOKEN"))'],{encoding:'utf8'});
const base=JSON.parse(zlib.gunzipSync(fs.readFileSync('research/strategy_engine/bitget-2026-07-10-15m.json.gz'))),steps={'1m':60,'5m':300,'15m':900,'1h':3600,'4h':14400};
function fixture(at){
 const windows={};for(const [tf,step]of Object.entries(steps)){
  // Only 15m/1h/4h are historical here; 1m/5m are labelled synthetic transport fixtures.
  let bars;if(step<900){bars=Array.from({length:201},(_,i)=>({time:Math.floor(at/step)*step-(200-i)*step,open:84000,high:84010,low:83990,close:84000,volume:1}));}
  else{const groups=new Map();for(const b of base.filter(b=>b.time<=at)){const t=Math.floor(b.time/step)*step;(groups.get(t)||groups.set(t,[]).get(t)).push(b);}bars=[...groups].map(([time,v])=>({time,open:v[0].open,high:Math.max(...v.map(x=>x.high)),low:Math.min(...v.map(x=>x.low)),close:v.at(-1).close,volume:v.reduce((s,x)=>s+x.volume,0)})).slice(-201);}
  windows[tf]={bars,event_at:at,received_at:at};
 }const p=windows['15m'].bars.at(-2).close;return {status:'LIVE',windows,quote:{source:'BITGET_USDT_FUTURES_BTCUSDT',time:at,received_at:at,bid:p-.01,ask:p+.01,last:p}};
}
let posts=0;const server=http.createServer((req,res)=>{if(req.method!=='GET'){posts++;res.writeHead(405).end();return;}if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end(html);return;}if(req.url.startsWith('/api/')){res.writeHead(503,{'Content-Type':'application/json'}).end('{}');return;}const p=path.resolve(root,'.'+req.url.split('?')[0]);if(!p.startsWith(root+'/static/')||!fs.existsSync(p)){res.writeHead(404).end();return;}res.setHeader('Content-Type',p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'image/svg+xml');res.end(fs.readFileSync(p));});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser,activePage;const report=[];
try{browser=await chromium.launch({...(process.env.CHROMIUM?{executablePath:process.env.CHROMIUM}:{}),args:['--no-sandbox']});
for(const mobile of [false,true]){
 const ctx=await browser.newContext(mobile?devices['Pixel 7']:{});await ctx.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());const page=await ctx.newPage(),errors=[];activePage=page;page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{window.__now=1790871300;Date.now=()=>window.__now*1000;window.WebSocket=class{constructor(){this.readyState=1;}send(){}close(){this.readyState=3;}};});
 await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>window.AuraManualStrategies&&window.AuraManualForwardObserver);
 const deliver=async s=>page.evaluate(s=>{window.__now=s.quote.time;window.__market=s;const h=window.AuraManualLiveHub;h.stop();h.windows=s.windows;h.quote=s.quote;h.status=s.status;h.emit();window.dispatchEvent(new CustomEvent('aura-manual-market',{detail:s}));},s);
 await deliver(fixture(1790871300));await page.waitForFunction(()=>document.getElementById('aura-signal-center').textContent.includes('Trend Pullback · 15m · LONG'));
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.getByRole('button',{name:'Перенести LONG в ручную форму · без сделки'}).first().click();assert.ok(Number(await page.locator('#mp-stop').inputValue())>0);assert.equal(posts,0);
 // Render the closed scenario chart lines using the actual chart event path.
 await page.evaluate(()=>{const b=__market.windows['15m'].bars;if(!chart)initializeChart();timeframe='15m';candles.setData(b);window.dispatchEvent(new CustomEvent('aura-manual-market',{detail:__market}));});
 await page.waitForFunction(()=>scenarioPriceLines.length===3);
 if(mobile){const box=await page.locator('#chart').boundingBox();await page.touchscreen.tap(box.x+80,box.y+80);await page.locator('#timeframes button[data-tf="1h"]').click();await page.locator('#timeframes button[data-tf="15m"]').click();}
 await page.screenshot({path:path.join(out,mobile?'mobile.png':'desktop.png'),fullPage:true});
 await deliver(fixture(1791212400));await page.waitForFunction(()=>document.getElementById('aura-signal-center').textContent.includes('Breakout + Retest · 15m · SHORT'));
 const stale=fixture(1791212400);stale.status='STALE';await deliver(stale);await page.waitForFunction(()=>scenarioPriceLines.length===0);assert.match(await page.locator('#aura-signal-center').textContent(),/REJECTED/);
 const n=await page.evaluate(()=>AuraManualForwardObserver.items.length);await page.reload();await page.waitForFunction(()=>window.AuraManualForwardObserver);assert.equal(await page.evaluate(()=>AuraManualForwardObserver.items.length),n);
 assert.deepEqual(errors,[]);report.push({mobile,touch:mobile,long:true,short:true,staleRejected:true,linesCleared:true,reloadJournal:true,copyNoOrders:true,errors});await ctx.close();
}
assert.equal(posts,0);fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({mode:'OFFLINE_HISTORICAL_OHLC_MODELED_QUOTES',physical_android:false,posts,report},null,2));console.log(JSON.stringify({status:'PASS',posts,report}));
}catch(error){if(activePage&&!activePage.isClosed()){fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify(await activePage.evaluate(()=>({panel:document.getElementById('aura-signal-center')?.textContent,quote:window.__market?.quote,now:Date.now()/1000,hub:window.AuraManualLiveHub?.diagnostic,body:document.body.dataset})),null,2));await activePage.screenshot({path:path.join(out,'failure.png'),fullPage:true});}throw error;}finally{await browser?.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});

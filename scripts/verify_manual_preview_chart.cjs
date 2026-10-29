/* Local Chromium regression. Replays a public Bitget REST capture; no trades or credentials.
 * Run: node scripts/verify_manual_preview_chart.cjs work/chart-check
 * Requires installed playwright, Chromium and repository Python dependencies. */
const fs=require('node:fs'),http=require('node:http'),path=require('node:path'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const {chromium,devices}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.argv[2]||'work/chart-check');
process.chdir(root);fs.mkdirSync(out,{recursive:true});
const html=execFileSync(process.env.PYTHON||'.venv/bin/python',['-c','from app.manual_preview.page import page; print(page("DUMMY_LOCAL_TOKEN"))'],{encoding:'utf8'});
const capture=JSON.parse(fs.readFileSync('tests/fixtures/manual_preview_bitget_15m.json')),now=capture.requestTime/1000+1,steps={'1m':60,'5m':300,'15m':900,'1h':3600,'4h':14400};
const rows=Object.fromEntries(Object.entries(steps).map(([tf,step])=>[tf,tf==='15m'?capture.data:Array.from({length:201},(_,i)=>[String((Math.floor(now/step)*step-(200-i)*step)*1000),'100','102','99','101','2','202'])]));
const replies=Object.fromEntries(Object.keys(steps).map(tf=>[tf,{code:'00000',requestTime:capture.requestTime,data:rows[tf]}]));
let posts=0,requests=0;
const server=http.createServer((req,res)=>{
 if(req.method!=='GET'){posts++;res.writeHead(405).end();return;}
 if(req.url.startsWith('/api/preview/bitget/candles?')){requests++;const g=new URL(req.url,'http://localhost').searchParams.get('granularity'),tf=({'1H':'1h','4H':'4h'})[g]||g;res.setHeader('Content-Type','application/json');res.end(JSON.stringify(replies[tf]));return;}
 if(req.url.startsWith('/api/')){res.writeHead(503,{'Content-Type':'application/json'}).end('{}');return;}
 if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end(html);return;}
 const p=path.join(root,req.url.split('?')[0]);if(!p.startsWith(path.join(root,'static')+path.sep)||!fs.existsSync(p)){res.writeHead(404).end();return;}
 res.setHeader('Content-Type',p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'image/svg+xml');res.end(fs.readFileSync(p));
});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{browser=await chromium.launch({executablePath:process.env.CHROMIUM||'/usr/bin/chromium',args:['--no-sandbox']});const report=[];
 for(const mobile of [false,true]){const ctx=await browser.newContext(mobile?devices['Pixel 7']:{}),page=await ctx.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(({now})=>{Date.now=()=>now*1000+performance.now();window.__sockets=[];window.WebSocket=class{constructor(){this.readyState=1;window.__sockets.push(this);setTimeout(()=>this.onopen?.(),10);}send(){}close(){this.readyState=3;this.onclose?.();}};},{now});
 await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>window.AuraManualLiveHub?.ws);
 const state=()=>page.evaluate(()=>({bars:candles.data().length,ema20:ema20.data().length,ema50:ema50.data().length,hidden:document.getElementById('chart-overlay').hidden,feed:document.getElementById('feed-state').textContent,close:candles.data().at(-1)?.close,status:window.AuraManualLiveHub.status,copy:document.getElementById('ml-copy').disabled}));
 let s=await state();assert.equal(s.bars,200);assert.ok(s.ema20&&s.ema50&&s.hidden&&s.copy);assert.match(s.feed,/HISTORY ONLY/);
 for(const tf of Object.keys(steps)){await page.click('#timeframes button[data-tf="'+tf+'"]');await page.waitForFunction(tf=>currentData?.timeframe===tf,tf);assert.equal((await state()).bars,200);}
 await page.click('#timeframes button[data-tf="15m"]');
 const deliver=async()=>page.evaluate(({rows,now})=>{const ws=window.AuraManualLiveHub.ws;for(const [tf,channel]of Object.entries(window.AuraManualLiveFeed.CHANNELS)){const data=rows[tf].map(r=>r.slice());ws.onmessage({data:JSON.stringify({arg:{instType:'USDT-FUTURES',instId:'BTCUSDT',channel},action:'snapshot',ts:now*1000,data})});}const price=Number(rows['15m'].at(-1)[4]);ws.onmessage({data:JSON.stringify({arg:{instType:'USDT-FUTURES',instId:'BTCUSDT',channel:'ticker'},action:'snapshot',ts:now*1000,data:[{bidPr:String(price),askPr:String(price+.1),lastPr:String(price),ts:now*1000}]})});},{rows,now});
 await deliver();await page.waitForFunction(()=>document.getElementById('feed-state').textContent==='LIVE');s=await state();assert.equal(s.status,'LIVE');assert.equal(s.bars,201);
 const updated=await page.evaluate(({now})=>{const hub=window.AuraManualLiveHub,b=hub.windows['15m'].bars.at(-1),close=b.close+1;hub.ws.onmessage({data:JSON.stringify({arg:{instType:'USDT-FUTURES',instId:'BTCUSDT',channel:'candle15m'},action:'update',ts:now*1000,data:[[String(b.time*1000),String(b.open),String(Math.max(b.high,close)),String(b.low),String(close),String(b.volume+1),'0']]})});return close;},{now});await page.waitForFunction(value=>candles.data().at(-1)?.close===value,updated);assert.equal((await state()).close,updated);
 await page.evaluate(()=>window.AuraManualLiveHub.ws.onclose());s=await state();assert.equal(s.status,'STALE');assert.equal(s.bars,200);assert.ok(s.hidden&&s.copy);assert.match(s.feed,/HISTORY ONLY/);
 await page.waitForFunction(()=>window.AuraManualLiveHub.status==='RECONNECTING'&&window.AuraManualLiveHub.ws.readyState===1);await deliver();await page.waitForFunction(()=>document.getElementById('feed-state').textContent==='LIVE');assert.equal((await state()).status,'LIVE');assert.ok(Number(await page.locator('#live-events').textContent())>0);
 // Replayed market data is explicitly labelled in evidence.
 await page.evaluate(()=>{const e=document.createElement('p');e.textContent='LOCAL REGRESSION · BITGET CAPTURE REPLAY · NOT DEPLOYED';document.body.prepend(e);});
 await page.screenshot({path:path.join(out,mobile?'mobile.png':'desktop.png'),fullPage:true});await page.locator('.chart-panel').screenshot({path:path.join(out,mobile?'mobile-chart.png':'desktop-chart.png')});assert.deepEqual(errors,[]);report.push({mobile,historyBars:200,liveBars:201,update:true,disconnectPreservesHistory:true,recovery:true,errors});await ctx.close();}
 assert.equal(posts,0);fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({mode:'LOCAL_CAPTURE_REPLAY',posts,requests,report},null,2));console.log(JSON.stringify({status:'PASS',posts,report}));
 }finally{await browser?.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

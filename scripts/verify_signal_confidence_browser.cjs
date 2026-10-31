/* Real desktop/Pixel 7 page, offline public-market fixtures only. No account calls. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {chromium,devices}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.argv[2]||'work/confidence-browser');
fs.mkdirSync(out,{recursive:true});
const html=execFileSync(process.env.PYTHON||'python',['-c','from app.manual_preview.page import page; print(page("DUMMY",server_signals=True))'],{cwd:root,encoding:'utf8'});
let mode='LIVE',posts=0;
const SOURCE='BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2',VERSION='AURA5_TECHNICAL_SCORE_V1_FROZEN';
function snapshot(){const now=Date.now()/1000,closed=Math.floor(now/300)*300;
 const quote={source:SOURCE,bid:49999.9,ask:50000.1,last:50000,time:now,received_at:now};
 const candidate={id:'a'.repeat(64),score_version:VERSION,score_model_sha256:'d'.repeat(64),model_sha256:'b'.repeat(64),input_sha256:'c'.repeat(64),
  score:80,score_groups:{trend:30,momentum:25,structure:10,volume:0,support_resistance:15},
  factors:['EMA group','RSI/MACD group'],contradictions:['volume'],direction:'LONG',frame:'5m',source:SOURCE,
  symbol:'BTCUSDT',closed_at:closed,observed_at:now,valid_until:closed+300,quote_time:now,quote_received_at:now,
  bid:quote.bid,ask:quote.ask,entry:quote.ask,sl:49700,tp:50750,net_rr:2.2,risk_gates_passed:true,
  costs:{stop_fees:100,target_fees:100,funding_reserve:5},technical_trigger:false,
  statistical_status:'UNVALIDATED',probability_tp_before_sl:null,manual_only:true,exchange_execution:false,
  cancel:'stale or expired',state:'WATCH_RESEARCH'};
 return {scope:'AURA6_PUBLIC_OBSERVER_ONLY',state:'NO TRADE',source:SOURCE,execution_enabled:false,
  account_connected:false,server_time:now,fresh_frames:['5m'],quotes:{'5m':quote},observer:{running:true,cycles:7,frame_errors:{}},
  records:[],alerts:[],watch_alerts:[],model_sha256:'b'.repeat(64),confidence_version:VERSION,
  confidence_candidates:mode==='STALE'?[]:[candidate]};}
const server=http.createServer((req,res)=>{
 if(req.method!=='GET'){posts++;res.writeHead(405).end();return;}
 if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end(html);return;}
 if(req.url==='/api/preview/signals/snapshot'){
  if(mode==='OFFLINE'){res.writeHead(503).end();return;}
  res.setHeader('Content-Type','application/json');res.end(JSON.stringify(snapshot()));return;}
 if(req.url.startsWith('/api/')){res.writeHead(503,{'Content-Type':'application/json'}).end('{}');return;}
 const file=path.resolve(root,'.'+req.url.split('?')[0]);
 if(!file.startsWith(root+'/static/')||!fs.existsSync(file)){res.writeHead(404).end();return;}
 res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'image/svg+xml');res.end(fs.readFileSync(file));
});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;const reports=[];
 try{browser=await chromium.launch({...(process.env.CHROMIUM?{executablePath:process.env.CHROMIUM}:{}),args:['--no-sandbox']});
 for(const mobile of [false,true]){mode='LIVE';const context=await browser.newContext(mobile?devices['Pixel 7']:{});
  const page=await context.newPage(),errors=[];
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{window.WebSocket=class{constructor(){this.readyState=1;}send(){}close(){this.readyState=3;}};});
  await page.goto('http://127.0.0.1:'+server.address().port);
  await page.waitForFunction(()=>document.querySelector('#aura-confidence .sc-cards')?.textContent.includes('LONG'));
  assert.match(await page.locator('#aura-confidence').textContent(),/НЕ вероятность прибыли/);
  assert.match(await page.locator('#aura-confidence').textContent(),/80\/100/);
  await page.locator('#aura-confidence .sc-controls button').click();
  await page.waitForFunction(()=>document.querySelector('#aura-confidence .sc-controls span')?.textContent.includes('Web Audio запланирован'));
  assert.equal(await page.evaluate(()=>new Aura5Confidence.LocalJournal(localStorage).rows[0].alerted_at!==null),true);
  await page.waitForTimeout(4300);
  assert.equal(await page.evaluate(()=>new Aura5Confidence.LocalJournal(localStorage).rows.filter(r=>r.alerted_at!==null).length),1);
  await page.locator('#aura-confidence input[type="range"]').evaluate(e=>{e.value='81';e.dispatchEvent(new Event('input',{bubbles:true}));});
  assert.equal(await page.locator('#aura-confidence .sc-cards article').count(),0);
  await page.locator('#aura-confidence input[type="range"]').evaluate(e=>{e.value='50';e.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.getByRole('button',{name:'Перенести LONG · без ордера'}).click();
  await page.waitForFunction(()=>document.getElementById('sc-manual-tp').value==='50750.0');
  assert.equal(await page.locator('#sc-manual-sl').inputValue(),'49700.0');
  assert.equal(await page.locator('#mp-entry').inputValue(),''); // PAPER controls untouched
  await page.locator('#sc-manual-sl').fill('49600');await page.locator('#sc-manual-sl').dispatchEvent('change');
  assert.equal(await page.evaluate(()=>Aura5Confidence&&new Aura5Confidence.LocalJournal(localStorage).rows[0].manual_adjustments.length),1);
  mode='OFFLINE';await page.waitForFunction(()=>document.querySelector('#aura-confidence [role="status"]')?.textContent.includes('OFFLINE'));
  assert.equal(await page.locator('#aura-confidence .sc-cards article').count(),0);
  mode='LIVE';await page.waitForFunction(()=>document.querySelector('#aura-confidence .sc-cards')?.textContent.includes('LONG'));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,mobile?'mobile.png':'desktop.png'),fullPage:true});
  assert.deepEqual(errors,[]);reports.push({mobile,threshold:true,copy_only:true,manual_edit:true,sound_optin_dedup:true,stale_recovery:true,page_errors:errors});
  await context.close();}
  assert.equal(posts,0);fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({status:'PASS',posts,reports},null,2));
  console.log(JSON.stringify({status:'PASS',posts,reports}));
 }finally{await browser?.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});

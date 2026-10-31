/* Offline Playwright journey of the real isolated server-signals HTML.
 * All price/signal inputs below are synthetic transport fixtures, never market evidence.
 */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {chromium,devices}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.argv[2]||'work/issue73-browser');
fs.mkdirSync(out,{recursive:true});
const html=execFileSync(process.env.PYTHON||'python',['-c',
  'from app.manual_preview.page import page; print(page("ISSUE73_FIXTURE",server_signals=True))'],{cwd:root,encoding:'utf8'});
const SOURCE='BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2',VERSION='AURA5_TECHNICAL_SCORE_V1_FROZEN';
let mode='LIVE',posts=0;
function snapshot(){const now=Date.now()/1000,closed=Math.floor(now/300)*300;
  const q={source:SOURCE,bid:49999.9,ask:50000.1,last:50000,time:now,received_at:now};
  const c={id:'a'.repeat(64),score_version:VERSION,score_model_sha256:'d'.repeat(64),model_sha256:'b'.repeat(64),input_sha256:'c'.repeat(64),
    score:75,score_groups:{trend:30,momentum:20,structure:10,volume:5,support_resistance:10},
    factors:['UNIT_FIXTURE_NOT_MARKET'],contradictions:['volume'],direction:'SHORT',frame:'5m',source:SOURCE,
    symbol:'BTCUSDT',closed_at:closed,observed_at:now,valid_until:closed+300,quote_time:now,quote_received_at:now,
    bid:q.bid,ask:q.ask,entry:q.bid,sl:50300,tp:49000,net_rr:2.2,risk_gates_passed:true,
    costs:{stop_fees:100,target_fees:100,funding_reserve:5,cost_version:'AURA5_EXIT_QUOTE_COSTS_2',entry_basis:'EXECUTABLE_QUOTE'},
    statistical_status:'UNVALIDATED',probability_tp_before_sl:null,manual_only:true,exchange_execution:false,
    cancel:'stale or expired',state:'WATCH_RESEARCH'};
  return {scope:'AURA6_PUBLIC_OBSERVER_ONLY',state:'NO TRADE',source:SOURCE,execution_enabled:false,
    account_connected:false,server_time:now,fresh_frames:['5m'],quotes:{'5m':mode==='STALE'?{...q,time:now-12}:q},
    observer:{running:true,cycles:8,frame_errors:{}},records:[],alerts:[],watch_alerts:[],
    model_sha256:'b'.repeat(64),confidence_version:VERSION,confidence_candidates:[c]};
}
const server=http.createServer((req,res)=>{
  if(req.method!=='GET'){posts++;res.writeHead(405).end();return;}
  if(req.url==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);return;}
  if(req.url==='/api/preview/signals/snapshot'){
    if(mode==='OFFLINE'){res.writeHead(503).end();return;}
    res.setHeader('Content-Type','application/json');res.end(JSON.stringify(snapshot()));return;
  }
  if(req.url.startsWith('/api/')){res.writeHead(503,{'Content-Type':'application/json'}).end('{}');return;}
  const file=path.resolve(root,'.'+req.url.split('?')[0]);
  if(!file.startsWith(root+'/static/')||!fs.existsSync(file)){res.writeHead(404).end();return;}
  res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'image/svg+xml');res.end(fs.readFileSync(file));
});

(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;const reports=[];
  try{
    browser=await chromium.launch({...(process.env.CHROMIUM?{executablePath:process.env.CHROMIUM}:{}),args:['--no-sandbox']});
    const configurations=[['desktop',{}],['pixel7',devices['Pixel 7']],
      ['samsung-a50-360',{viewport:{width:360,height:740},deviceScaleFactor:2,isMobile:true,hasTouch:true}]];
    for(const [name,config] of configurations){
      mode='LIVE';const context=await browser.newContext(config),page=await context.newPage(),errors=[];
      await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
      await page.addInitScript(()=>{window.WebSocket=class{constructor(){this.readyState=1;}send(){}close(){this.readyState=3;}};});
      page.on('pageerror',e=>errors.push(e.message));
      await page.goto('http://127.0.0.1:'+server.address().port);
      await page.waitForFunction(()=>document.querySelector('#app-signal-state')?.textContent.includes('SHORT'));
      assert.equal(await page.locator('[role="tab"]').count(),4);
      assert.equal(await page.locator('#app-home').isVisible(),true);
      assert.equal(await page.locator('#app-signals').isVisible(),false);
      assert.match(await page.locator('#app-bid-ask').textContent(),/Bid 49,999\.90 · Ask 50,000\.10/);
      assert.match(await page.locator('#app-signal-detail').textContent(),/Entry .*SL .*TP .*net RR/);
      assert.match(await page.locator('#app-signal-state').textContent(),/SHORT · WATCH · 75\/100/);
      await page.getByRole('button',{name:'Смотреть сигналы'}).click();
      assert.equal(await page.locator('#app-signals').isVisible(),true);
      assert.equal(await page.locator('#app-tab-signals').getAttribute('aria-selected'),'true');
      assert.equal(await page.locator('#aura-confidence input[type="range"]').count(),1);
      await page.locator('#aura-confidence input[type="range"]').evaluate(e=>{e.value='76';e.dispatchEvent(new Event('input',{bubbles:true}));});
      await page.locator('#app-tab-home').click();
      await page.waitForFunction(()=>document.querySelector('#app-signal-state')?.textContent==='WAIT');
      await page.locator('#app-tab-signals').click();
      await page.locator('#aura-confidence input[type="range"]').evaluate(e=>{e.value='50';e.dispatchEvent(new Event('input',{bubbles:true}));});
      await page.locator('#app-tab-home').click();await page.waitForFunction(()=>document.querySelector('#app-signal-state')?.textContent.includes('SHORT'));
      await page.locator('#app-tab-chart').click();
      assert.equal(await page.locator('#chart').isVisible(),true);
      assert.ok((await page.locator('#chart').boundingBox()).width>100);
      assert.equal(await page.locator('#drawing-tool').count(),1);
      assert.equal(await page.locator('#timeframes [data-tf="5m"]').count(),1);
      await page.locator('#app-tab-more').click();
      assert.equal(await page.locator('#manual-paper-panel').count(),1);
      assert.equal(await page.locator('#aura-confidence details').count(),0); // Journal moved into More
      const journal=page.locator('.aura-more-card details').first();assert.equal(await journal.count(),1);
      await journal.locator('summary').click();
      assert.match(await journal.textContent(),/Локальный журнал/);
      await page.locator('#app-theme').selectOption('light');
      assert.equal(await page.locator('body').getAttribute('data-aura-theme'),'light');
      await page.locator('#app-tab-home').click();
      assert.equal(await page.locator('#app-home').isVisible(),true);
      await page.goBack();assert.equal(await page.locator('#app-more').isVisible(),true);
      await page.goForward();assert.equal(await page.locator('#app-home').isVisible(),true);
      mode='STALE';await page.waitForFunction(()=>document.querySelector('#app-signal-state')?.textContent==='STALE');
      assert.equal(await page.locator('#app-bid-ask').textContent(),'Bid — · Ask —');
      mode='OFFLINE';await page.waitForFunction(()=>document.querySelector('#app-signal-detail')?.textContent.includes('Нет связи'));
      mode='LIVE';await page.waitForFunction(()=>document.querySelector('#app-signal-state')?.textContent.includes('SHORT'));
      const nav=await page.locator('.aura-bottom-nav').boundingBox(),size=page.viewportSize();
      assert.ok(nav.y+nav.height>=size.height-2);
      for(const key of ['home','signals','chart','more'])assert.ok((await page.locator('#app-tab-'+key).boundingBox()).height>=44);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
      await page.screenshot({path:path.join(out,name+'-home.png'),fullPage:true});
      await page.locator('#app-tab-signals').click();await page.screenshot({path:path.join(out,name+'-signals.png'),fullPage:true});
      assert.deepEqual(errors,[]);reports.push({name,nav:true,home_freshness:true,threshold:true,chart:true,
        manual_journal:true,theme:true,history:true,offline_recovery:true,no_post:true,page_errors:errors});
      await context.close();
    }
    assert.equal(posts,0);
    fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({status:'PASS',fixture:'SOFTWARE_ONLY_NOT_BITGET_MARKET_EVIDENCE',posts,reports},null,2));
    console.log(JSON.stringify({status:'PASS',posts,reports}));
  }finally{await browser?.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});

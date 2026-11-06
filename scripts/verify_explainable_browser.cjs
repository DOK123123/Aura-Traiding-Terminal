/* Actual preview HTML in desktop/Android Chromium. Archived values are transport
 * fixtures with shifted times, not evidence of current live connectivity. GET only. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process'),{chromium,devices}=require('playwright');
const root=path.resolve(__dirname,'..'),out=path.resolve(process.argv[2]||'work/explainable-browser');fs.mkdirSync(out,{recursive:true});
const py=process.env.PYTHON||'python';
const html=execFileSync(py,['-c','from app.manual_preview.page import page; print(page("EXPLAINABLE_DUMMY",server_signals=True))'],{encoding:'utf8',cwd:root});
const fixture=JSON.parse(execFileSync(py,['-c',`
import gzip,json
from scripts.replay_explainable import bars_for
from app.manual_preview.explainable import evaluate
from app.hunter.market import SOURCE
base=json.load(gzip.open('research/strategy_engine/bitget-2026-07-10-15m.json.gz'))
at=1787464800
b=[r for r in bars_for(base,3600) if r[0]+3600<=at][-260:];mid=b[-1][4]
q=dict(source=SOURCE,bid=mid*.9999,ask=mid*1.0001,last=mid,time=at,received_at=at)
rows=[]
for frame,step in [('15m',900),('1h',3600),('4h',14400)]:
 b=[r for r in bars_for(base,step) if r[0]+step<=at][-260:]
 rows.extend(evaluate(b,frame,q,at))
b=[r for r in bars_for(base,3600) if r[0]+3600<=at][-260:]
mirror=[[t,2*mid-o,2*mid-l,2*mid-h,2*mid-c,v] for t,o,h,l,c,v in b]
long=next(r for r in evaluate(mirror,'1h',q,at) if r['strategy']=='BREAKOUT_RETEST' and r['direction']=='LONG')
assert long['state']=='WATCH'
print(json.dumps(dict(rows=rows,quote=q,long_fixture=long,bars=b[-201:])))
`],{encoding:'utf8',cwd:root}));
let mode='LIVE',posts=0,ticks=0;const held=new Set();
function snapshot(){const now=Date.now()/1000,q={...fixture.quote,time:now,received_at:now},steps={'5m':300,'15m':900,'1h':3600,'4h':14400};
 const delta=++ticks*.02;q.bid-=delta;q.ask+=delta;
 const candidates=structuredClone(fixture.rows).map(c=>({...c,closed_at:Math.floor(now/steps[c.frame])*steps[c.frame],valid_until:(Math.floor(now/steps[c.frame])+1)*steps[c.frame],quote_time:now,quote_received_at:now,entry:c.entry==null?null:q[c.direction==='LONG'?'ask':'bid']}));
 if(mode==='LONG'){const at=Math.floor(now/3600)*3600,c={...fixture.long_fixture,closed_at:at,valid_until:at+3600,quote_time:now,quote_received_at:now,entry:q.ask};candidates.push(c);}
 return {scope:'AURA6_PUBLIC_OBSERVER_ONLY',source:q.source,execution_enabled:false,account_connected:false,server_time:now,
 observer:{running:true,cycles:1,frame_errors:{}},fresh_frames:Object.keys(steps),quotes:Object.fromEntries(Object.keys(steps).map(tf=>[tf,q])),
 explanation_version:'AURA5_EXPLAINABLE_V1',explainable_candidates:mode==='MALFORMED'?{invalid:true}:candidates,records:[],alerts:[],watch_alerts:[],confidence_candidates:[]};}
const server=http.createServer((req,res)=>{if(req.method!=='GET'){posts++;res.writeHead(405).end();return;}
 if(req.url==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);return;}
 if(req.url==='/api/preview/signals/snapshot'){if(mode==='HOLD'){held.add(res);res.on('close',()=>held.delete(res));return;}if(mode==='OFFLINE'){res.writeHead(503).end();return;}res.setHeader('Content-Type','application/json');res.end(JSON.stringify(snapshot()));return;}
 if(req.url.startsWith('/api/preview/bitget/candles?')&&req.url.includes('granularity=1H&')){
  const now=Date.now(), last=Math.floor(now/3600000)*3600, first=last-(fixture.bars.length-1)*3600;
  const data=fixture.bars.map((r,i)=>[String((first+i*3600)*1000),...r.slice(1).map(String),'0']);
  res.setHeader('Content-Type','application/json');res.end(JSON.stringify({code:'00000',requestTime:now,data}));return;
 }
 if(req.url.startsWith('/api/')){res.writeHead(503,{'Content-Type':'application/json'}).end('{}');return;}
 const file=path.resolve(root,'.'+req.url.split('?')[0]);if(!file.startsWith(root+'/static/')||!fs.existsSync(file)){res.writeHead(404).end();return;}
 res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'image/svg+xml');res.end(fs.readFileSync(file));});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;const reports=[];
 try{browser=await chromium.launch({...(process.env.CHROMIUM?{executablePath:process.env.CHROMIUM}:{}),args:['--no-sandbox']});
 for(const [name,config] of [['desktop',{}],['pixel7',devices['Pixel 7']],['poco-f7',{viewport:{width:432,height:960},isMobile:true,hasTouch:true}],['a50',{viewport:{width:360,height:740},isMobile:true,hasTouch:true}]]){
 mode='LIVE';ticks=0;const context=await browser.newContext(config),page=await context.newPage(),errors=[];
 await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 await page.addInitScript(()=>{window.addEventListener('aura-preview-snapshot',e=>{window.lastSignalSnapshot=e.detail;});window.WebSocket=class{constructor(){this.readyState=1;}send(){}close(){}};});page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:'+server.address().port);await page.locator('#app-tab-signals').click();
 await page.waitForFunction(()=>document.querySelector('#aura-explainable [data-frame="1h"][data-direction="SHORT"]')?.dataset.state==='WATCH');
 assert.equal(await page.locator('#aura-explainable article').count(),8);
 await page.getByRole('button',{name:'Включить звук WATCH · открытая вкладка',exact:true}).click();
 await page.waitForFunction(()=>document.getElementById('aura-explainable').textContent.includes('Web Audio запланирован'));
 const watch=page.locator('#aura-explainable [data-frame="1h"][data-direction="SHORT"]');
 assert.match(await watch.textContent(),/Breakout \+ Retest/);assert.match(await watch.textContent(),/Почему SL здесь/);assert.match(await watch.textContent(),/Почему TP здесь/);assert.doesNotMatch(await watch.textContent(),/max_seconds|Entry time/);
 await page.locator('#explain-risk').fill('25');assert.match(await watch.textContent(),/Размер позиции ≤/);
 await watch.locator('summary').click();
 const entry=await watch.locator('dd').first().textContent();
 await watch.evaluate(e=>{window.savedCard=e;window.savedDetails=e.querySelector('details');window.savedBody=e.querySelector('details div').firstChild;window.savedId=e.dataset.scenarioId;});
 await page.waitForFunction(value=>window.savedCard.querySelector('dd').textContent!==value,entry);
 assert.equal(await watch.evaluate(e=>e===window.savedCard&&e.dataset.scenarioId===window.savedId&&e.querySelector('details')===window.savedDetails&&window.savedDetails.open&&window.savedBody.isConnected),true);
 await page.evaluate(()=>{
  for(let i=0;i<120;i++){
   const d=structuredClone(window.lastSignalSnapshot),now=Date.now()/1000;d.server_time=now;
   for(const q of Object.values(d.quotes)){q.time=q.received_at=now;}
   for(const c of d.explainable_candidates){c.quote_time=c.quote_received_at=now;}
   window.dispatchEvent(new CustomEvent('aura-preview-snapshot',{detail:d}));
   if(window.savedCard!==document.querySelector('#aura-explainable [data-frame="1h"][data-direction="SHORT"]'))throw Error('CARD_DISAPPEARED');
  }
 });
 await watch.getByRole('button',{name:'Закрепить сигнал',exact:true}).click();
 const frozen=await watch.textContent();
 await page.evaluate(()=>{for(let i=0;i<120;i++)window.dispatchEvent(new CustomEvent('aura-preview-snapshot',{detail:structuredClone(window.lastSignalSnapshot)}));});
 assert.equal(await watch.textContent(),frozen);assert.match(frozen,/СНИМОК/);
 await watch.getByRole('button',{name:'Открепить снимок',exact:true}).click();
 assert.ok(await page.locator('.explain-history li').count()>0);
 assert.match(await watch.textContent(),/ATR14/);assert.match(await watch.textContent(),/funding-резерв/);
 assert.equal(await page.locator('#aura-score-diagnostics').getAttribute('open'),null);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});
 await watch.getByRole('button',{name:'На графике'}).click();
 await page.waitForFunction(()=>explainLines.length===3&&explainZones.length>0&&currentData?.timeframe==='1h');
 assert.match(await page.locator('#aura-explain-chart-legend').textContent(),/SHORT.+Entry.+SL.+TP/);
 mode='HOLD';await page.waitForFunction(()=>[...document.querySelectorAll('#aura-explainable article')].every(e=>e.dataset.state==='UNKNOWN'),{},{timeout:15000});
 await page.waitForFunction(()=>explainLines.length===0&&explainZones.length===0);
 await page.locator('#app-tab-signals').click();
 assert.match(await watch.locator('strong').textContent(),/НЕАКТУАЛЕН/);
 assert.equal(await watch.locator('dd').first().isVisible(),true);
 assert.equal(await watch.getByRole('button',{name:'На графике'}).count(),0);
 assert.equal(await watch.locator('details').getAttribute('open'),'');
 mode='LONG';for(const res of held)res.destroy();held.clear();
 await page.waitForFunction(()=>document.querySelector('#aura-explainable [data-frame="1h"][data-direction="LONG"]')?.dataset.state==='WATCH',{},{timeout:20000});
 await page.locator('#aura-explainable [data-frame="1h"][data-direction="LONG"]').getByRole('button',{name:'На графике'}).click();
 await page.waitForFunction(()=>explainLines.length===3&&document.getElementById('aura-explain-chart-legend').textContent.startsWith('LONG'));
 await page.screenshot({path:path.join(out,name+'-chart.png'),fullPage:true});
 mode='MALFORMED';await page.waitForFunction(()=>[...document.querySelectorAll('#aura-explainable article')].every(e=>e.dataset.state==='UNKNOWN'),{},{timeout:10000});
 for(const tab of ['chart','more','home','signals'])await page.locator('#app-tab-'+tab).click();
 await page.reload();await page.locator('#app-tab-signals').click();await page.waitForFunction(()=>document.querySelector('.explain-history li'));
 assert.match(await page.locator('.explain-history').textContent(),/НЕАКТУАЛЕН/);
 assert.deepEqual(errors,[]);reports.push({name,long_short:true,rejected_unknown:true,risk:true,details_persist:true,stable_dom:true,updates:240,pin:true,persistent_history:true,chart_overlays:true,quote_expiry:true,navigation:true,overflow:false,errors});await context.close();}
 assert.equal(posts,0);fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({status:'PASS',posts,reports},null,2));console.log(JSON.stringify({status:'PASS',posts,reports}));
 }finally{for(const res of held)res.destroy();await browser?.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});


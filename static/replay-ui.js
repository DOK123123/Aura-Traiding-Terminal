/* Preview-only independent historical chart. No live feed, account, copy or order events. */
(function(){'use strict';if(document.body.dataset.manualPreview!=='true')return;
const R=window.AuraHistoricalReplay,host=document.getElementById('aura-replay');if(!R||!host)return;
host.innerHTML=`<h2>Проверка стратегий · Historical Replay</h2>
<p class="analyst-warning">ИСТОРИЯ · НЕ LIVE. Те же три стратегии, только закрытые свечи. Bid/Ask отсутствуют: модельный спред 0,02%, проскальзывание 0,05% и комиссия 0,10% на сторону. UNVALIDATED / NO_VALIDATED_EDGE. Это проверка обнаружения, не доказательство прибыли. Сделки не создаются.</p>
<div class="replay-controls">
<label>Источник<select id="rp-source"><option value="archive">Сохранённые реальные свечи Bitget · июль–октябрь 2026</option><option value="bitget">Загрузить из Bitget API</option></select></label>
<label>Начало UTC<input id="rp-start" type="date" value="2026-10-01"></label>
<label>Конец UTC · не включая<input id="rp-end" type="date" value="2026-10-29"></label>
<label>Таймфрейм<select id="rp-tf"><option>15m</option><option>1h</option><option>4h</option></select></label>
<label>Скорость<select id="rp-speed"><option value="1">×1 · свеча/сек</option><option value="10">×10</option><option value="50">×50</option><option value="100">×100</option><option value="max">Максимально быстро</option></select></label>
<button id="rp-load" type="button">Загрузить период</button></div>
<div class="replay-actions"><button id="rp-play" type="button">Старт</button><button id="rp-pause" type="button">Пауза</button><button id="rp-next" type="button">Следующая свеча</button><button id="rp-signal" type="button">Следующий сигнал</button><button id="rp-reset" type="button">Сброс</button></div>
<p id="rp-status" role="status">Выберите период. Лимит — 6000 свечей + 200 свечей прогрева. LIVE работает отдельно.</p><progress id="rp-progress" max="1" value="0"></progress><p id="rp-count"></p>
<div id="rp-chart" aria-label="Исторический график Replay"></div><div id="rp-plan"></div>
<details><summary>Журнал исторических сценариев · последние 100 в интерфейсе</summary><ol id="rp-journal"></ol></details>
<button id="rp-json" type="button">Экспорт JSON</button><button id="rp-csv" type="button">Экспорт CSV</button>`;
const el=k=>document.getElementById('rp-'+k);let replay=null,running=false,generation=0,timer=null,abort=null,loading=false,chart=null,series=null,lines=[];
function pause(){running=false;generation++;clearTimeout(timer);if(replay&&replay.status==='RUNNING')replay.status='PAUSED';}
function controls(){for(const k of ['play','pause','next','signal','json','csv'])el(k).disabled=!replay||loading||(['play','next','signal'].includes(k)&&replay.done);for(const k of ['source','start','end','tf','load'])el(k).disabled=loading;}
function draw(){
 if(!replay)return;
 if(!chart){chart=window.LightweightCharts.createChart(el('chart'),{autoSize:true,height:300,layout:{background:{color:'#101720'},textColor:'#c5d2e4'},timeScale:{timeVisible:true},handleScroll:true,handleScale:true});series=chart.addSeries(window.LightweightCharts.CandlestickSeries);}
 series.setData(replay.visible);for(const line of lines)series.removePriceLine(line);lines=[];
 const selected=replay.latest.find(x=>['LONG','SHORT'].includes(x.state));
 if(selected)for(const [k,label,color]of [['entry','Replay Entry','#f4c779'],['stop','Replay SL','#fa788b'],['target','Replay TP','#42d6b0']])lines.push(series.createPriceLine({price:selected[k],title:label,color,lineWidth:1,lineStyle:2}));
 chart.timeScale().scrollToRealTime();
}
function render(){
 controls();if(!replay)return;
 el('progress').max=replay.total;el('progress').value=replay.counts.processed;
 el('count').textContent='Обработано '+replay.counts.processed+' / '+replay.total+' · LONG '+replay.counts.LONG+' · SHORT '+replay.counts.SHORT+' · REJECTED '+replay.counts.REJECTED+' · WAIT '+replay.counts.WAIT;
 el('status').textContent='ИСТОРИЯ · '+replay.status+' · '+replay.payload.source+' · автопауза при каждом LONG/SHORT. LIVE не остановлен.';
 el('plan').replaceChildren();
 for(const x of replay.latest.filter(x=>x.setup!=='WAIT')){const p=document.createElement('p');p.textContent=x.name+' · '+x.state+' · '+new Date(x.formed_at*1000).toISOString()+' · Entry '+x.entry.toFixed(2)+' · SL '+x.stop.toFixed(2)+' · TP '+x.target.toFixed(2)+' · net R/R '+(x.net_rr?.toFixed(2)||'—')+' · '+x.edge+'. '+[...x.reasons,...x.rejection].join('; ')+'. Отмена: '+x.cancel;el('plan').append(p);}
 el('journal').replaceChildren();for(const x of replay.journal.slice(-100).reverse()){const li=document.createElement('li');li.textContent=new Date(x.formed_at*1000).toISOString()+' '+x.name+' '+x.setup+' → '+x.state+' · '+x.rejection.join('; ');el('journal').append(li);}
 draw();
}
function advance(){const rows=replay.next();if(rows.some(x=>['LONG','SHORT'].includes(x.state))||replay.done)pause();return rows;}
function tick(gen,seek){
 if(!running||gen!==generation)return;
 try{const fast=seek||el('speed').value==='max',until=performance.now()+8;
  do{advance();if(!running)break;}while(fast&&performance.now()<until);
  render();if(running)timer=setTimeout(()=>tick(gen,seek),fast?0:1000/Number(el('speed').value));
 }catch(e){pause();el('status').textContent='Replay остановлен: '+e.message;controls();}
}
function play(seek){if(!replay||replay.done||loading)return;pause();running=true;replay.status='RUNNING';tick(generation,seek);}
el('play').addEventListener('click',()=>play(false));el('signal').addEventListener('click',()=>play(true));el('pause').addEventListener('click',()=>{pause();render();});
el('next').addEventListener('click',()=>{if(!replay||replay.done||loading)return;pause();try{advance();render();}catch(e){el('status').textContent=e.message;}});
el('reset').addEventListener('click',()=>{pause();abort?.abort();abort=null;loading=false;if(replay){replay.reset();render();}else controls();});
for(const k of ['source','start','end','tf'])el(k).addEventListener('change',()=>{pause();replay=null;el('plan').replaceChildren();el('journal').replaceChildren();el('count').textContent='';el('progress').value=0;if(series)series.setData([]);for(const line of lines)series.removePriceLine(line);lines=[];el('status').textContent='Период изменён. Нажмите «Загрузить период».';controls();});
el('load').addEventListener('click',async()=>{
 pause();abort?.abort();const requestGeneration=generation,controller=new AbortController();abort=controller;loading=true;replay=null;el('plan').replaceChildren();el('journal').replaceChildren();if(series){series.setData([]);for(const line of lines)series.removePriceLine(line);lines=[];}controls();el('status').textContent='Загрузка реальных свечей и 200 свечей прогрева…';
 const deadline=setTimeout(()=>controller.abort(),65000);
 try{
  const start=Date.parse(el('start').value+'T00:00:00Z')/1000,end=Date.parse(el('end').value+'T00:00:00Z')/1000;
  if(!Number.isInteger(start)||!Number.isInteger(end)||end<=start)throw Error('Проверьте даты UTC');
  const params=new URLSearchParams({source:el('source').value,timeframe:el('tf').value,start:String(start),end:String(end)});
  const response=await fetch('/api/preview/bitget/history?'+params,{method:'GET',credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
  if(!response.ok)throw Error(response.status===401?'Войдите как владелец':response.status===400?'Неверный период или более 6000 свечей':response.status===429?'Загрузка уже идёт. Повторите позже':'Нет полного проверенного периода. Смените даты/источник');
  const payload=await response.json();if(requestGeneration!==generation)return;replay=new R.Replay(payload);loading=false;render();
 }catch(e){if(requestGeneration===generation){loading=false;el('status').textContent=e.name==='AbortError'?'Загрузка отменена или превышено время ожидания':e.message;controls();}}
 finally{clearTimeout(deadline);if(abort===controller)abort=null;}
});
for(const format of ['json','csv'])el(format).addEventListener('click',()=>{if(!replay)return;const report=replay.report(),blob=new Blob([format==='json'?JSON.stringify(report,null,2):R.csv(report)],{type:format==='json'?'application/json':'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='aura-historical-replay.'+format;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
document.addEventListener('visibilitychange',()=>{if(document.hidden){pause();render();}});window.addEventListener('pagehide',()=>{pause();abort?.abort();});
window.AuraReplayUI={get model(){return replay;},get running(){return running;}};controls();
})();

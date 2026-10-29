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
<div class="replay-actions"><button id="rp-play" type="button">Старт</button><button id="rp-pause" type="button">Пауза</button><button id="rp-next" type="button">Следующая свеча</button><button id="rp-signal" type="button">Следующий сигнал</button><button id="rp-analyze" type="button">Рассчитать исходы до конца</button><button id="rp-reset" type="button">Сброс</button></div>
<p id="rp-status" role="status">Выберите период. Лимит — 6000 свечей + 200 свечей прогрева. LIVE работает отдельно.</p><progress id="rp-progress" max="1" value="0"></progress><p id="rp-count"></p>
<div id="rp-chart" aria-label="Исторический график Replay"></div><div id="rp-plan"></div>
<details><summary>Журнал исторических сценариев · последние 100 в интерфейсе</summary><ol id="rp-journal"></ol></details>
<details id="rp-results" open><summary>Результаты проверки · независимые гипотезы</summary>
<p>Модель: условный вход по касанию Entry только на следующей свече, срок удержания 96 свечей, 1 BTC на гипотезу. Касание не доказывает реальное исполнение. При SL и TP внутри свечи — SL; неясный порядок Entry/TP — UNKNOWN. Комиссии/спред/проскальзывание модельные, funding не учтён. UNKNOWN и неисполненные сигналы исключены из PnL. UNVALIDATED / NO_VALIDATED_EDGE.</p>
<p id="rp-result-status" role="status"></p>
<div class="rp-table-wrap" tabindex="0" aria-label="Статистика по стратегии и направлению"><table id="rp-stats"></table></div>
<label>Кривая результата · отдельная группа<select id="rp-curve-group"></select></label>
<p>Сумма R независимых гипотез по времени закрытия, а не капитал или доходность портфеля. Пересечения позиций не моделируются. Время входа/выхода известно только до свечи.</p>
<canvas id="rp-equity" height="220" role="img" aria-label="Кривая накопленной суммы R независимых гипотез"></canvas><p id="rp-curve-text"></p>
<details><summary>Результаты по месяцам UTC · месяц возникновения сигнала</summary><div class="rp-table-wrap" tabindex="0"><table id="rp-months"></table></div></details>
<details open><summary>Таблица гипотетических сделок · последние 200, все в экспорте</summary><div class="rp-table-wrap" tabindex="0"><table id="rp-trades"></table></div></details>
<button id="rp-outcome-json" type="button">Результаты JSON</button><button id="rp-outcome-csv" type="button">Результаты CSV</button></details>
<button id="rp-json" type="button">Экспорт JSON</button><button id="rp-csv" type="button">Экспорт CSV</button>`;
const el=k=>document.getElementById('rp-'+k);let replay=null,running=false,generation=0,timer=null,abort=null,loading=false,chart=null,series=null,lines=[];
function pause(){running=false;generation++;clearTimeout(timer);if(replay&&replay.status==='RUNNING')replay.status='PAUSED';}
function controls(){for(const k of ['play','pause','next','signal','analyze','json','csv','outcome-json','outcome-csv'])el(k).disabled=!replay||loading||(['play','next','signal','analyze'].includes(k)&&replay.done);for(const k of ['source','start','end','tf','load'])el(k).disabled=loading;}
function draw(){
 if(!replay)return;
 if(!chart){chart=window.LightweightCharts.createChart(el('chart'),{autoSize:true,height:300,layout:{background:{color:'#101720'},textColor:'#c5d2e4'},timeScale:{timeVisible:true},handleScroll:true,handleScale:true});series=chart.addSeries(window.LightweightCharts.CandlestickSeries,{autoscaleInfoProvider:base=>{const info=base(),signal=replay?.latest.find(x=>['LONG','SHORT'].includes(x.state));if(!info?.priceRange||!signal)return info;return {...info,priceRange:{minValue:Math.min(info.priceRange.minValue,signal.entry,signal.stop,signal.target),maxValue:Math.max(info.priceRange.maxValue,signal.entry,signal.stop,signal.target)}};}});}
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
 draw();renderResults();
}

const number=v=>v===null||v===undefined?'—':Number(v).toFixed(2);
function table(id,headers,rows){const target=el(id);target.replaceChildren();const head=document.createElement('thead'),tr=document.createElement('tr');for(const label of headers){const th=document.createElement('th');th.scope='col';th.textContent=label;tr.append(th);}head.append(tr);target.append(head);const body=document.createElement('tbody');for(const row of rows){const tr=document.createElement('tr');for(const value of row){const td=document.createElement('td');td.textContent=value;tr.append(td);}body.append(tr);}target.append(body);}
function renderResults(){
 if(!replay){for(const id of ['stats','months','trades','curve-group'])el(id).replaceChildren();el('result-status').textContent='Загрузите период для расчёта.';el('curve-text').textContent='';el('equity').getContext('2d').clearRect(0,0,el('equity').width,el('equity').height);return;}
 const report=replay.outcomeReport(),stats=report.statistics,headers=['Группа','Сигналы','Входы','Закрыто','UNKNOWN','Без входа','Неоднозначные','Win Rate %','PF','Средняя прибыль USDT','Средний убыток USDT','Expectancy R','PnL USDT · 1 BTC','Max DD USDT','Max DD R'];
 const row=(key,m)=>[key,m.signals,m.entered,m.resolved,m.unknown,m.not_filled,m.ambiguous,number(m.win_rate===null?null:m.win_rate*100),number(m.profit_factor),number(m.average_profit_usdt),number(m.average_loss_usdt),number(m.expectancy_R),number(m.pnl_usdt),number(m.max_drawdown_usdt),number(m.max_drawdown_R)];
 table('stats',headers,Object.entries(stats.groups).map(([k,m])=>row(k,m)));table('months',headers,Object.entries(stats.months).map(([k,m])=>row(k,m)));
 el('result-status').textContent=(report.complete?'Период обработан.':'ЧАСТИЧНЫЙ РАСЧЁТ: обработано '+replay.counts.processed+' свечей. OPEN/PENDING ещё не имеют исхода.')+' UNKNOWN не считается выигрышем. PF не определён при отсутствии убытков. Доходность портфеля не рассчитывается.';
 const date=v=>v===null?'—':new Date(v*1000).toISOString();
 table('trades',['Стратегия','Направление','Сигнал UTC','Entry','SL','TP','Исход','Вход UTC','Выход UTC','Fill вход','Fill выход','Комиссии','PnL USDT','R','Неоднозначно','Причина'],report.trades.slice(-200).reverse().map(t=>[t.strategy,t.direction,date(t.signal_time),number(t.entry),number(t.sl),number(t.tp),t.outcome,date(t.entry_time),date(t.exit_time),number(t.entry_fill),number(t.exit_fill),number(t.fees_usdt),number(t.pnl_usdt),number(t.r),t.ambiguous?'Да':'Нет',t.note]));
 const previous=el('curve-group').value;el('curve-group').replaceChildren();for(const key of Object.keys(stats.groups)){const option=document.createElement('option');option.value=key;option.textContent=key;el('curve-group').append(option);}if(stats.groups[previous])el('curve-group').value=previous;drawCurve();
}
function drawCurve(){
 const canvas=el('equity'),ctx=canvas.getContext('2d'),width=Math.max(280,canvas.clientWidth),height=220,dpr=window.devicePixelRatio||1;canvas.width=width*dpr;canvas.height=height*dpr;ctx.scale(dpr,dpr);ctx.fillStyle='#101720';ctx.fillRect(0,0,width,height);
 const metrics=replay?.outcomeReport().statistics.groups[el('curve-group').value],curve=metrics?.curve||[];if(!curve.length){el('curve-text').textContent='Нет определённых закрытых исходов для кривой.';return;}
 const values=[0,...curve.map(p=>p.cumulative_R)],min=Math.min(...values),max=Math.max(...values),range=max-min||1,x=i=>40+i*(width-60)/Math.max(1,values.length-1),y=v=>180-(v-min)*150/range;
 ctx.strokeStyle='#536279';ctx.beginPath();ctx.moveTo(40,y(0));ctx.lineTo(width-20,y(0));ctx.stroke();ctx.strokeStyle='#42d6b0';ctx.lineWidth=2;ctx.beginPath();values.forEach((v,i)=>i?ctx.lineTo(x(i),y(v)):ctx.moveTo(x(i),y(v)));ctx.stroke();ctx.fillStyle='#c5d2e4';ctx.font='12px sans-serif';ctx.fillText(number(max)+' R',4,18);ctx.fillText(number(min)+' R',4,205);
 el('curve-text').textContent=el('curve-group').value+' · '+curve.length+' закрытых исходов · сумма '+number(values.at(-1))+' R · max DD '+number(metrics.max_drawdown_R)+' R · '+new Date(curve[0].time*1000).toISOString().slice(0,10)+' — '+new Date(curve.at(-1).time*1000).toISOString().slice(0,10);
}
el('curve-group').addEventListener('change',drawCurve);window.addEventListener('resize',drawCurve);
for(const format of ['json','csv'])el('outcome-'+format).addEventListener('click',()=>{if(!replay)return;const report=replay.outcomeReport(),blob=new Blob([format==='json'?JSON.stringify(report,null,2):window.AuraTradeOutcomes.csv(report)],{type:format==='json'?'application/json':'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='aura-trade-outcomes.'+format;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});

function advance(all=false){const rows=replay.next();if(!all&&rows.some(x=>['LONG','SHORT'].includes(x.state))||replay.done)pause();return rows;}
function tick(gen,seek,all=false){
 if(!running||gen!==generation)return;
 try{const fast=seek||el('speed').value==='max',until=performance.now()+8;
  do{advance(all);if(!running)break;}while(fast&&performance.now()<until);
  render();if(running)timer=setTimeout(()=>tick(gen,seek,all),fast?0:1000/Number(el('speed').value));
 }catch(e){pause();el('status').textContent='Replay остановлен: '+e.message;controls();}
}
function play(seek,all=false){if(!replay||replay.done||loading)return;pause();running=true;replay.status='RUNNING';tick(generation,seek,all);}
el('analyze').addEventListener('click',()=>play(true,true));
el('play').addEventListener('click',()=>play(false));el('signal').addEventListener('click',()=>play(true));el('pause').addEventListener('click',()=>{pause();render();});
el('next').addEventListener('click',()=>{if(!replay||replay.done||loading)return;pause();try{advance();render();}catch(e){el('status').textContent=e.message;}});
el('reset').addEventListener('click',()=>{pause();abort?.abort();abort=null;loading=false;if(replay){replay.reset();render();}else{el('status').textContent='Сброшено. Выберите период и загрузите историю.';controls();renderResults();}});
for(const k of ['source','start','end','tf'])el(k).addEventListener('change',()=>{pause();replay=null;el('plan').replaceChildren();el('journal').replaceChildren();el('count').textContent='';el('progress').value=0;if(series)series.setData([]);for(const line of lines)series.removePriceLine(line);lines=[];el('status').textContent='Период изменён. Нажмите «Загрузить период».';controls();renderResults();});
el('load').addEventListener('click',async()=>{
 pause();abort?.abort();const requestGeneration=generation,controller=new AbortController();abort=controller;loading=true;replay=null;renderResults();el('plan').replaceChildren();el('journal').replaceChildren();if(series){series.setData([]);for(const line of lines)series.removePriceLine(line);lines=[];}controls();el('status').textContent='Загрузка реальных свечей и 200 свечей прогрева…';
 const deadline=setTimeout(()=>controller.abort(),65000);
 try{
  const start=Date.parse(el('start').value+'T00:00:00Z')/1000,end=Date.parse(el('end').value+'T00:00:00Z')/1000;
  if(!Number.isInteger(start)||!Number.isInteger(end)||end<=start)throw Error('Проверьте даты UTC');
  const params=new URLSearchParams({source:el('source').value,timeframe:el('tf').value,start:String(start),end:String(end)});
  const response=await fetch('/api/preview/bitget/history?'+params,{method:'GET',credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
  if(!response.ok)throw Error(response.status===401?'Войдите как владелец':response.status===400?'Неверный период или более 6000 свечей':response.status===429?'Загрузка уже идёт. Повторите позже':'Нет полного проверенного периода. Смените даты/источник');
  const payload=await response.json();if(requestGeneration!==generation)return;if(payload.start!==start||payload.end!==end||payload.timeframe!==params.get('timeframe')||payload.source!==(params.get('source')==='archive'?'BITGET_SAVED_REAL_ARCHIVE_2026_07_01_TO_10_29':'BITGET_PUBLIC_HISTORY_API'))throw Error('Источник или период ответа не совпал с запросом');replay=new R.Replay(payload);loading=false;render();
 }catch(e){if(requestGeneration===generation){loading=false;el('status').textContent=e.name==='AbortError'?'Загрузка отменена или превышено время ожидания':e.message;controls();}}
 finally{clearTimeout(deadline);if(abort===controller)abort=null;}
});
for(const format of ['json','csv'])el(format).addEventListener('click',()=>{if(!replay)return;const report=replay.report(),blob=new Blob([format==='json'?JSON.stringify(report,null,2):R.csv(report)],{type:format==='json'?'application/json':'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='aura-historical-replay.'+format;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
document.addEventListener('visibilitychange',()=>{if(document.hidden){pause();render();}});window.addEventListener('pagehide',()=>{pause();abort?.abort();});
window.AuraReplayUI={get model(){return replay;},get running(){return running;},get levels(){const x=replay?.latest.find(v=>['LONG','SHORT'].includes(v.state));return x&&series?['entry','stop','target'].map(key=>({key,price:x[key],y:series.priceToCoordinate(x[key])})):[];}};controls();
})();

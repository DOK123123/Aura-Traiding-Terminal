'use strict';
(() => {
  let activeController=null, generation=0, busy=false, latest=null, previewChart=null, automatic=true, lastRun=0;
  const p=id=>document.getElementById(id);
  const number=(v,d=2)=>v==null?'—':Number(v).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
  const when=t=>new Date(t*1000).toISOString().replace('T',' ').slice(0,16);
  const value=id=>Number(p('pattern-'+id).value);
  const date=id=>p('pattern-'+id).value?Math.floor(Date.parse(p('pattern-'+id).value+'Z')/1000):null;
  const selected=()=>({symbol:p('symbol').value,timeframe:document.querySelector('[data-tf][aria-pressed="true"]').dataset.tf,context:Number(p('limit').value)});
  function requestBody(){
    for(const input of document.querySelectorAll('.pattern-controls input[type="number"]')){
      if(!input.checkValidity())throw new Error('Проверьте настройку: '+input.parentElement.textContent.trim());
    }
    return {...selected(),config:{lookback:value('lookback'),max_matches:value('matches'),minimum_similarity:value('similarity'),
      signal_threshold:value('threshold'),minimum_sample:value('sample'),minimum_confidence:value('confidence'),
      horizons:p('pattern-horizons').value.split(',').map(Number),decision_horizon:value('horizon'),round_trip_cost_bps:value('cost')}};
  }
  function tableRow(parent,values){const tr=document.createElement('tr');for(const v of values){const td=document.createElement('td');if(v instanceof Node)td.append(v);else td.textContent=String(v);tr.append(td);}parent.append(tr);}
  function clear(){latest=null;p('pattern-result').hidden=true;p('backtest-result').hidden=true;p('pattern-preview').hidden=true;if(previewChart){previewChart.remove();previewChart=null;}}
  function controls(disabled){for(const id of ['run','point','backtest'])p('pattern-'+id).disabled=disabled;}
  function preview(index){
    const m=latest.top_matches[index];p('pattern-preview').hidden=false;
    p('pattern-preview-title').textContent=`Аналог ${when(m.time)} UTC · справа от отметки — известный исторический исход`;
    if(previewChart)previewChart.remove();
    const L=window.LightweightCharts;
    previewChart=L.createChart(p('pattern-chart'),{autoSize:true,layout:{background:{color:'#111720'},textColor:'#93a1b4'},timeScale:{timeVisible:true},grid:{vertLines:{color:'#222c39'},horzLines:{color:'#222c39'}}});
    const series=previewChart.addSeries(L.CandlestickSeries,{upColor:'#42d6b0',downColor:'#fa788b',borderVisible:false,wickUpColor:'#42d6b0',wickDownColor:'#fa788b'});
    series.setData(m.candles);
    L.createSeriesMarkers(series,[{time:m.time,position:'aboveBar',color:'#e5bd70',shape:'arrowDown',text:'MATCH END'}]);
    previewChart.timeScale().fitContent();
  }
  function render(data){
    latest=data;p('pattern-result').hidden=false;p('backtest-result').hidden=true;
    p('pattern-mode').textContent=data.mode;p('pattern-signal').textContent=data.signal;
    p('pattern-score').textContent=number(data.confidence)+'%';p('pattern-count').textContent=data.historical_matches;
    p('pattern-average').textContent=number(data.average_similarity)+'%';
    p('pattern-meta').textContent=`${data.symbol} · ${data.timeframe} · ${data.source} · решение ${when(data.as_of)} UTC · контекст ${data.context} · архив ${data.archive_bars} свечей (${when(data.archive_first)} — ${when(data.archive_last)} UTC). ${data.data_note}`;
    p('pattern-warning').textContent=(data.low_sample_size?'LOW SAMPLE SIZE · ':'')+(data.status==='DELAYED'?'DELAYED · ':'')+`Горизонт решения: ${data.config.decision_horizon} свечей. Нижняя граница Wilson: ${number(data.wilson_lower_pct)}%. Confidence не является вероятностью.`;
    const outcomes=p('pattern-outcomes');outcomes.replaceChildren();
    for(const [h,s] of Object.entries(data.outcomes))tableRow(outcomes,[h,`${s.up} (${number(s.up_pct)}%)`,`${s.down} (${number(s.down_pct)}%)`,s.flat,...['average_move_pct','median_move_pct','max_positive_pct','max_negative_pct','mfe_pct','mae_pct'].map(k=>number(s[k]))]);
    const top=p('pattern-top');top.replaceChildren();
    data.top_matches.forEach((m,i)=>{const button=document.createElement('button');button.className='pattern-match';button.textContent=when(m.time);button.addEventListener('click',()=>preview(i));const result=m.outcomes[String(data.config.decision_horizon)];tableRow(top,[button,number(m.similarity)+'%',number(m.outcomes['5']?.move_pct)+'%',number(m.outcomes['20']?.move_pct)+'%',`${result.move_pct>0?'UP':result.move_pct<0?'DOWN':'FLAT'} ${number(result.move_pct)}% / ${data.config.decision_horizon} свечей`]);});
    if(!data.top_matches.length)tableRow(top,['Нет аналогов выше заданного порога','—','—','—','WAIT']);
    p('pattern-reasons').replaceChildren();
    for(const [key,title] of [['bullish','Bullish factors'],['bearish','Bearish factors'],['evidence','Calculated evidence'],['risks','Risk factors']]){
      const block=document.createElement('div'),heading=document.createElement('h4'),list=document.createElement('ul');heading.textContent=title;
      for(const reason of data.explanation[key]){const item=document.createElement('li');item.textContent=reason;list.append(item);}block.append(heading,list);p('pattern-reasons').append(block);
    }
    p('pattern-actual').textContent=data.actual_after_point?'Фактический исход после точки (исключён из расчёта сигнала): '+Object.entries(data.actual_after_point).map(([h,v])=>`${h} свечей: ${v?number(v.move_pct)+'%':'ещё нет данных'}`).join(' · '):'Анализ только закрытых свечей. Обновляется отдельно от live-графика.';
  }
  function renderBacktest(data){
    p('pattern-result').hidden=true;p('backtest-result').hidden=false;
    p('backtest-meta').textContent=`${data.symbol} · ${data.timeframe} · ${data.source} · архив ${data.archive_bars}. ${data.method} ${data.truncated?'Показаны первые решения в пределах заданного лимита.':''}`;
    p('backtest-summary').replaceChildren();
    for(const [key,title] of [['total_decisions','Total decisions'],['total_signals','Total signals'],['wins','Wins'],['losses','Losses'],['win_rate','Win rate %'],['average_return_pct','Average net return %'],['profit_factor','Profit factor'],['max_drawdown_pct','Max drawdown %'],['long_accuracy','LONG accuracy %'],['short_accuracy','SHORT accuracy %'],['wait_frequency','WAIT frequency %']]){
      const block=document.createElement('div'),label=document.createElement('span'),strong=document.createElement('strong');label.textContent=title;strong.textContent=number(data.summary[key]);block.append(label,strong);p('backtest-summary').append(block);
    }
    p('backtest-rows').replaceChildren();for(const row of data.points)tableRow(p('backtest-rows'),[when(row.as_of),row.signal,number(row.confidence)+'%',row.historical_matches,number(row.actual_close_move_pct),number(row.net_return_pct)]);
  }
  async function run(mode='current'){
    if(busy)return;
    const id=++generation;activeController=new AbortController();busy=true;controls(true);lastRun=Date.now();
    clear();p('pattern-status').textContent='Загрузка реального архива и расчёт… live-график продолжает работать.';
    const timeout=setTimeout(()=>activeController?.abort(),150000);
    try{
      const body=requestBody();
      if(mode==='point'){body.as_of=date('asof');if(!body.as_of)throw new Error('Укажите историческую точку UTC.');}
      if(mode==='backtest'){body.start_at=date('start');body.end_at=date('end');body.max_points=value('points');}
      const response=await fetch('/api/patterns/'+(mode==='backtest'?'backtest':'analyze'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:activeController.signal});
      const data=await response.json();if(id!==generation)return;
      if(!response.ok)throw new Error(data.message||JSON.stringify(data.detail)||'Источник недоступен');
      if(mode==='backtest')renderBacktest(data);else render(data);
      p('pattern-status').textContent=`${data.status} · ${mode==='backtest'?'BACKTEST':data.mode} · рассчитано ${new Date().toISOString().slice(11,19)} UTC`;
    }catch(error){if(id!==generation)return;clear();p('pattern-status').textContent='NO DATA · '+(error.name==='AbortError'?'Превышено время ожидания. Повторите анализ.':error.message);}
    finally{clearTimeout(timeout);if(id===generation){busy=false;controls(false);}}
  }
  function changed(){generation++;activeController?.abort();busy=false;controls(false);clear();automatic=true;lastRun=0;p('pattern-status').textContent='NO DATA · Параметры изменены. Ожидаем анализ нового рынка.';}
  p('pattern-run').addEventListener('click',()=>{automatic=true;run();});
  p('pattern-point').addEventListener('click',()=>{automatic=false;run('point');});
  p('pattern-backtest').addEventListener('click',()=>{automatic=false;run('backtest');});
  for(const id of ['symbol','limit'])p(id).addEventListener('change',changed);
  p('timeframes').addEventListener('click',event=>{if(event.target.closest('[data-tf]'))changed();});
  document.querySelector('.pattern-controls').addEventListener('change',changed);
  setInterval(()=>{if(automatic&&p('pattern-auto').checked&&!busy&&Date.now()-lastRun>=60000)run();},2000);
})();

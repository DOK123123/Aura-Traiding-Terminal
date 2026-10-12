// Isolated owner-only research UI. No Paper, Auto Paper or exchange requests.
(() => {
  const el = id => document.getElementById('lab-' + id);
  const names = {AURA_EXISTING:'Aura Existing',DONCHIAN:'Donchian Breakout',TREND_ATR:'Trend + ATR',EMA_RSI_ADX:'EMA + RSI + ADX'};
  let report = null, busy = false, generation = 0, stopped = false, selected = null, nextOffset = 0;
  const controllers = new Set();
  const show = v => v === null || v === undefined ? '—' : String(v);
  const utc = value => new Date(value*1000).toISOString();
  const status = value => { el('status').textContent = value; };
  function controls() {
    for(const id of ['run','list-refresh','replay','more','timeframe','split','experiments']) el(id).disabled = busy || stopped;
    for(const button of el('comparison').querySelectorAll('button')) button.disabled = busy || stopped;
  }
  async function request(path,body) {
    const controller = new AbortController();controllers.add(controller);
    const timer = setTimeout(() => controller.abort(),105000);
    try {
      const options = {credentials:'same-origin',cache:'no-store',signal:controller.signal};
      if(body!==undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-Aura-Lab':'research-only'};options.body=JSON.stringify(body);}
      const response = await fetch('/api/lab/'+path,options);el('login').hidden = response.status!==401;
      if(response.status===401 || response.status===403) throw new Error('Owner access required: aura / configured owner password.');
      const data = await response.json();
      if(!response.ok) throw new Error(data.message || 'Research request failed.');
      return data;
    } finally {clearTimeout(timer);controllers.delete(controller);}
  }
  function safe(data) {
    if(data.symbol!=='BTCUSDT' || data.safety?.research_only!==true || data.safety?.activation_available!==false || data.safety?.real_money_execution!=='DISABLED' || !Array.isArray(data.runs)) throw new Error('Invalid research identity; result hidden.');
  }
  function cell(row,value) {const c=document.createElement('td');c.textContent=show(value);row.append(c);}
  function comparison() {
    generation++;selected=null;el('detail').hidden=true;el('comparison').replaceChildren();
    if(!report)return;
    const tf=el('timeframe').value,split=el('split').value,rank=report.rankings[tf];
    el('ranking').textContent = split==='validation' ? `Best numerical result: ${show(names[rank.best_numerical])}. Eligible order (≥20 trades): ${rank.qualified_order.map(n=>names[n]).join(', ') || 'none — inconclusive'}. ${rank.criterion}` : 'Development only: no validation ranking or parameter selection here.';
    for(const data of report.runs.filter(r=>r.timeframe===tf && r.split===split)) {
      const row=document.createElement('tr'),name=document.createElement('td'),button=document.createElement('button');
      button.textContent=names[data.strategy];button.addEventListener('click',()=>detail(data.strategy,0));name.append(button);row.append(name);
      if(split==='validation' && rank.best_numerical===data.strategy)row.className='lab-best';
      if(data.status!=='OK') {cell(row,data.status);cell(row,data.reason);el('comparison').append(row);continue;}
      cell(row,data.metrics.sample_status);
      for(const key of ['net_profit','return_pct','trades','win_rate','profit_factor','expectancy','max_drawdown_pct','average_win','average_loss','realized_risk_reward','sharpe'])cell(row,data.metrics[key]);
      el('comparison').append(row);
    }
  }
  function render(data) {
    safe(data);report=data;el('result').hidden=false;
    el('meta').textContent=`${data.version} · Snapshot ${data.dataset_id} · Config frozen before validation · Source ${data.source}`;
    el('coverage').textContent=`Common UTC coverage ${utc(data.dataset_start)} — ${utc(data.dataset_end_exclusive)} exclusive; split ${utc(data.split_at)} (${data.actual_development_pct}% development). `+
      Object.entries(data.coverage).map(([tf,c])=>`${tf}: ${c.candles} test / ${c.warmup_bars} warm-up, DEV ${c.development_candles}, VALID ${c.validation_candles}`).join(' · ');
    el('export').href='/api/lab/experiments/'+encodeURIComponent(data.id)+'/export';comparison();
  }
  async function list() {
    if(busy || stopped)return;busy=true;controls();
    try {
      const rows=await request('experiments');el('experiments').replaceChildren();
      const blank=document.createElement('option');blank.value='';blank.textContent='Select saved experiment';el('experiments').append(blank);
      for(const row of rows){const o=document.createElement('option');o.value=row.id;o.textContent=utc(row.coverage_end)+' · '+row.id.slice(0,12);el('experiments').append(o);}
      status('Saved immutable studies loaded. No live strategy state changed.');
    }catch(error){status(error.message);}finally{busy=false;controls();}
  }
  async function run() {
    if(busy || stopped)return;
    const start=el('start').value,end=el('end').value;
    const body={days:Number(el('days').value),development_pct:el('development').value.trim(),fee_bps:el('fee').value.trim(),slippage_bps:el('slippage').value.trim(),
      start:start?Date.parse(start+'Z')/1000:null,end:end?Date.parse(end+'Z')/1000:null};
    busy=true;generation++;const id=generation;controls();el('result').hidden=true;status('Fetching closed history / frozen research comparison. Maximum 60s fetch + 30s compute; no activation.');
    try {const data=await request('run',body);if(id!==generation || stopped)return;render(data);status('Comparison complete. Validation ranking is descriptive, never production authorization.');}
    catch(error){if(id===generation && !stopped){el('result').hidden=true;status(error.message+' If the response was lost, refresh saved studies before repeating.');}}
    finally{busy=false;controls();}
  }
  async function load() {
    if(busy || stopped)return;const ident=el('experiments').value;if(!ident)return;
    busy=true;const id=++generation;controls();el('result').hidden=true;
    try{const data=await request('experiments/'+encodeURIComponent(ident));if(id===generation && !stopped){render(data);status('Saved snapshot loaded; no recomputation or history refetch.');}}
    catch(error){status(error.message);}finally{busy=false;controls();}
  }
  async function replay() {
    if(busy || stopped || !report)return;busy=true;const id=generation;controls();
    try{const data=await request('experiments/'+encodeURIComponent(report.id)+'/replay',{});if(id!==generation || stopped)return;render(data);status('Snapshot replay identical. Parameters and stored data unchanged.');}
    catch(error){status(error.message);}finally{busy=false;controls();}
  }
  function draw(points) {
    const svg=el('curve');svg.replaceChildren();if(!points.length)return;
    const values=points.map(p=>Number(p.equity));if(!values.every(Number.isFinite))throw new Error('Invalid curve');
    const lo=Math.min(...values),hi=Math.max(...values),range=hi-lo || 1;
    const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');line.setAttribute('class','lab-line');
    line.setAttribute('points',values.map((v,i)=>`${10+(points[i].time-points[0].time)*580/Math.max(1,points.at(-1).time-points[0].time)},${145-(v-lo)*130/range}`).join(' '));svg.append(line);
  }
  async function detail(strategy,offset) {
    if(!report || stopped || busy)return;busy=true;controls();const id=++generation,tf=el('timeframe').value,split=el('split').value;selected=strategy;el('detail').hidden=true;
    try {
      const data=await request('experiments/'+encodeURIComponent(report.id)+'/detail?timeframe='+tf+'&split='+split+'&strategy='+encodeURIComponent(strategy)+'&offset='+offset+'&limit=100');
      if(id!==generation || stopped)return;
      el('detail-title').textContent=names[strategy]+' · '+tf+' · '+split;
      el('detail-note').textContent=(data.reason || data.curve_display)+` · trades ${offset}–${offset+data.trades.length} / ${data.trade_total}; full records in export.`;
      draw(data.equity_curve);el('trades').replaceChildren();
      for(const t of data.trades){const row=document.createElement('tr');for(const value of [t.direction,utc(t.signal_time),utc(t.entry_time),t.entry_price,t.size,t.stop_loss,t.take_profit,t.exit_price,t.fees,t.realized_pnl,t.exit_reason])cell(row,value);el('trades').append(row);}
      nextOffset=offset+data.trades.length;el('more').hidden=!data.has_more;el('detail').hidden=false;
    }catch(error){if(id===generation)status(error.message);}
    finally{busy=false;controls();}
  }
  el('run').addEventListener('click',run);el('list-refresh').addEventListener('click',list);el('experiments').addEventListener('change',load);el('replay').addEventListener('click',replay);
  el('more').addEventListener('click',()=>detail(selected,nextOffset));
  el('timeframe').addEventListener('change',comparison);el('split').addEventListener('change',comparison);
  window.addEventListener('pagehide',()=>{stopped=true;generation++;controllers.forEach(c=>c.abort());});
  window.addEventListener('pageshow',()=>{if(stopped)location.reload();});
})();

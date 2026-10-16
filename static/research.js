// Manual owner-only research; no trading/account/scheduler requests or polling.
(() => {
  const el=id=>document.getElementById('research-'+id);
  let busy=false,configured=false;
  const text=value=>value==null?'—':String(value);
  function controls(){for(const b of document.querySelectorAll('button'))b.disabled=busy || (b.id==='research-idea'&&!configured);}
  async function request(path='',body){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),240000);
    try{
      const options={credentials:'same-origin',cache:'no-store',signal:controller.signal};
      if(body!==undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-Aura-Lab':'research-only'};options.body=JSON.stringify(body);}
      const r=await fetch('/api/research'+path,options);
      if(r.status===401||r.status===403)throw new Error('Требуется вход владельца: aura / настроенный owner password.');
      const data=await r.json();if(!r.ok)throw new Error(data.code||'RESEARCH_UNAVAILABLE');return data;
    }finally{clearTimeout(timer);}
  }
  async function action(fn){if(busy)return;busy=true;controls();try{await fn();}catch(e){el('status').textContent=e.name==='AbortError'?'Ответ потерян. Обновите историю перед повтором.':e.message;}finally{busy=false;controls();}}
  function card(parent,title,body){const box=document.createElement('article'),h=document.createElement('strong'),p=document.createElement('p');box.className='card';h.textContent=title;p.textContent=body;box.append(h,p);parent.append(box);}
  function cell(row,value){const td=document.createElement('td');td.textContent=text(value);row.append(td);}
  function result(data){
    const r=data.report;el('result').hidden=true;if(!r){el('status').textContent=data.state;return;}
    if(r.research_only!==true||r.activation_available!==false||r.final_test_is_independent!==false)throw new Error('Invalid research boundary');
    el('result').hidden=false;
    el('audit').textContent=`${r.auditor.status} · ${r.auditor.reasons.join(' ')} · config ${r.config_hash}`;
    el('export').href='/api/research/experiments/'+encodeURIComponent(data.id)+'/export';
    el('metrics').replaceChildren();for(const run of r.runs){const row=document.createElement('tr');cell(row,run.split);cell(row,run.scale);for(const key of ['trades','net_profit','return_pct','profit_factor','win_rate','expectancy','max_drawdown_pct','sharpe','fees'])cell(row,run.metrics[key]);el('metrics').append(row);}
    el('audit-details').replaceChildren();for(const a of r.audits)card(el('audit-details'),`${a.split} / ${a.scale}: ${a.status}`,`${a.closed_trades_checked} trades; ${a.independent_math}`);
    el('status').textContent='Исследование завершено. Никакая стратегия не активирована.';
  }
  async function refresh(){
    const data=await request();if(data.research_only!==true||data.activation_available!==false||data.manual_only!==true)throw new Error('Invalid research identity');
    configured=data.llm.enabled===true;el('ai').textContent=data.llm.status+' · deterministic backtest/audit available';el('agents').replaceChildren();for(const a of data.agents)card(el('agents'),a.id+' · '+a.state,a.capabilities.join('; '));
    el('data').textContent=`${data.dataset.source} · ${data.dataset.total_candles} closed candles incl warmup · ${new Date(data.dataset.start*1000).toISOString()} → ${new Date(data.dataset.end_exclusive*1000).toISOString()} · SHA256 ${data.dataset.sha256}`;
    el('registry').replaceChildren();for(const h of Object.values(data.registry))card(el('registry'),h.title,h.rationale+' '+h.rules);
    el('sources').replaceChildren();for(const [id,s] of Object.entries(data.sources)){const p=document.createElement('p'),a=document.createElement('a');a.textContent=id+': '+s.title+' ('+s.year+')';if(s.url.startsWith('https://doi.org/'))a.href=s.url;a.rel='noopener noreferrer';a.target='_blank';p.append(a,document.createTextNode(' — '+s.scope));el('sources').append(p);}
    el('queue').replaceChildren();for(const q of data.queue){const row=document.createElement('tr');for(const k of ['id','hypothesis','state'])cell(row,q[k]);const td=document.createElement('td'),b=document.createElement('button');b.textContent=q.state==='QUEUED'?'Запустить вручную':'Результат';b.addEventListener('click',()=>action(async()=>{if(q.state==='QUEUED'){el('status').textContent='TESTING: изолированный backtest и аудит…';result(await request('/queue/'+encodeURIComponent(q.id)+'/run',{}));}else result(await request('/experiments/'+encodeURIComponent(q.id)));await refresh();}));td.append(b);if(q.state==='ERROR'){const retry=document.createElement('button');retry.textContent='Повторить тот же конфиг';retry.addEventListener('click',()=>action(async()=>{await request('/queue/'+encodeURIComponent(q.id)+'/retry',{});await refresh();el('status').textContent='Тот же конфиг снова в очереди. Запуск — отдельной кнопкой.';}));td.append(retry);}row.append(td);el('queue').append(row);}
    el('calls').textContent=JSON.stringify(data.llm_calls,null,2);
    el('published').textContent=data.published?data.published.experiments.map(e=>e.hypothesis+' — '+e.status+'\n'+e.runs.filter(r=>r.scale==='1').map(r=>r.split+': '+r.metrics.trades+' trades; net '+r.metrics.net_profit+' USDT; DD '+r.metrics.max_drawdown_pct+'%').join('\n')).join('\n\n'):'Опубликованных результатов нет.';
  }
  el('refresh').addEventListener('click',()=>action(async()=>{await refresh();el('status').textContent='История обновлена. Исследования автоматически не запускаются.';}));
  el('enqueue').addEventListener('click',()=>action(async()=>{const r=await request('/queue',{hypothesis:el('hypothesis').value});await refresh();el('status').textContent='Конфиг зафиксирован: '+r.id+'. Для вычисления нажмите «Запустить вручную».';}));
  el('recover').addEventListener('click',()=>action(async()=>{const r=await request('/recover-interrupted',{});await refresh();el('status').textContent='Прерванных задач отмечено: '+r.interrupted+'. Автоповтора нет.';}));
  el('idea').addEventListener('click',()=>action(async()=>{const r=await request('/ideas',{});el('proposal').textContent=JSON.stringify(r,null,2);await refresh();el('status').textContent='ADVISORY_ONLY_UNVERIFIED: идея не добавлена в исполняемый реестр.';}));
  // No initial fetch, timer, automatic job or LLM call.
})();

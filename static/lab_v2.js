/* Frozen research results only. No production controls or account requests. */
(()=>{'use strict';
 const names={AURA42:'Aura 4.2 native',AURA43:'Aura 4.3 original'};
 for(const p of ['DONCHIAN','TREND_ATR','EMA_RSI_ADX'])for(const tf of ['15m','1h','4h'])names[p+'_'+tf]=p+' · '+tf;
 function safe(data){return data?.research_only===true&&data.activation_available===false&&data.real_money_execution==='DISABLED'&&data.symbol==='BTCUSDT'&&data.version==='AURA_STRATEGY_LAB_2.0'&&Array.isArray(data.runs);}
 if(typeof module!=='undefined')module.exports={safe,names};
 if(typeof document==='undefined')return;
 const el=id=>document.getElementById('lv2-'+id);if(!el('panel'))return;
 let report=null,busy=false,generation=0,offset=0,stopped=false;const controllers=new Set();
 const show=x=>x==null?'—':String(x),utc=x=>typeof x==='number'?new Date(x*1000).toISOString():'—';
 function cell(row,value){const td=document.createElement('td');td.textContent=show(value);row.append(td);}
 function controls(){for(const id of ['refresh','split','variant','side','more'])el(id).disabled=busy||stopped;}
 async function request(path){const c=new AbortController();controllers.add(c);const timer=setTimeout(()=>c.abort(),30000);
  try{const r=await fetch('/api/lab/v2'+path,{credentials:'same-origin',cache:'no-store',signal:c.signal});
   if(r.status===401||r.status===403)throw Error('Войдите владельцем через ссылку aura.');const data=await r.json();if(!r.ok)throw Error(data.message||'Достоверный отчёт недоступен.');return data;
  }finally{clearTimeout(timer);controllers.delete(c);}}
 function table(){el('comparison').replaceChildren();if(!report)return;
  for(const r of report.runs.filter(r=>r.split===el('split').value)){const tr=document.createElement('tr');cell(tr,names[r.variant]);
   for(const k of ['trades','trades_per_30d','signals','net_profit','return_pct','win_rate','profit_factor','max_drawdown_pct','average_win','average_loss','expectancy','sharpe','fees','slippage','final_mode'])cell(tr,r.metrics[k]);
   cell(tr,r.metrics.sample_status);el('comparison').append(tr);}}
 function draw(series){const svg=el('curve');svg.replaceChildren();const all=series.flatMap(s=>s.points.map(p=>Number(p.equity)));
  if(!all.length||!all.every(Number.isFinite))return;const lo=Math.min(...all),range=Math.max(...all)-lo||1;
  for(const [i,s] of series.entries()){if(!s.points.length)continue;const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');const start=s.points[0].time,end=s.points.at(-1).time;
   line.setAttribute('fill','none');line.setAttribute('stroke',i?'#56d6b2':'#9ca9ff');line.setAttribute('stroke-width','2');line.setAttribute('points',s.points.map(p=>`${10+(p.time-start)*580/Math.max(1,end-start)},${150-(Number(p.equity)-lo)*135/range}`).join(' '));svg.append(line);}}
 async function detail(page=0){if(!report||busy||stopped)return;busy=true;controls();const g=++generation;
  try{const query='?split='+el('split').value+'&offset='+page+'&limit=100';const variant=el('variant').value;
   const [data,base]=await Promise.all([request('/detail'+query+'&variant='+variant+'&side='+el('side').value),request('/detail'+query+'&variant=AURA42')]);if(g!==generation||stopped)return;
   if([data,base].some(d=>d.research_only!==true||d.activation_available!==false||d.real_money_execution!=='DISABLED'))throw Error('Неверная идентичность detail-отчёта.');
   draw([{points:base.equity_curve},{points:data.equity_curve}]);el('trades').replaceChildren();el('decisions').replaceChildren();
   for(const t of data.trades){const tr=document.createElement('tr');for(const v of [t.direction,utc(t.original_signal_at??t.signal_at),utc(t.signal_at),utc(t.entry_time),t.entry_price,t.initial_stop_loss??t.stop_loss,t.stop_loss,t.take_profit,utc(t.exit_time),t.exit_price,t.fees,t.realized_pnl,t.reason,t.exit_reason,JSON.stringify(t.stop_history||[])])cell(tr,v);el('trades').append(tr);}
   for(const d of data.decisions){const tr=document.createElement('tr');for(const v of [utc(d.original_signal_at??d.closed_at),utc(d.closed_at),d.direction,JSON.stringify(Object.fromEntries(Object.entries(d.gates||{}).map(([side,gates])=>[side,Object.keys(gates).filter(k=>!gates[k])]))),d.strategy_reason,d.reason,JSON.stringify(d.context||{})])cell(tr,v);el('decisions').append(tr);}
   el('open').textContent=JSON.stringify({position:data.open_position,pending:data.pending},null,2);el('monthly').textContent=JSON.stringify(data.monthly,null,2);el('sides').textContent=JSON.stringify(data.side_results,null,2);
   el('counts').textContent=JSON.stringify({strategy_reasons:data.decision_counts,execution_rejections:data.execution_rejections,scenario_attribution:data.scenario_attribution},null,2);
   el('note').textContent=`${names[variant]} · ${el('split').value} · closed trades ${data.trade_total}; all evaluated TF decisions ${data.decision_total}; offset ${page}. Open position: ${data.open_position?'YES (marked, not force-closed)':'NO'}. Equity display ≤302 points including extrema.`;
   offset=data.next_offset;el('more').hidden=!data.has_more;
  }catch(e){el('status').textContent=e.message;el('trades').replaceChildren();el('decisions').replaceChildren();el('curve').replaceChildren();el('monthly').textContent='';el('counts').textContent='';el('sides').textContent='';el('open').textContent='';el('note').textContent='Детали недоступны.';el('more').hidden=true;}
  finally{busy=false;controls();}}
 async function load(){if(busy||stopped)return;busy=true;controls();el('result').hidden=true;
  try{const data=await request('');if(!safe(data))throw Error('Неверная идентичность research-отчёта.');report=data;
   el('status').textContent='Исследование завершено. Увеличение числа сделок не доказывает улучшение. Автоматическая активация отсутствует.';
   el('meta').textContent=`${utc(data.start)} — ${utc(data.end_exclusive)}; split ${utc(data.split_at)} · source SHA256 ${data.source.sha256}. 70% разработки / 30% проверки, без подбора по validation. Проверка не является полностью слепым holdout.`;
   el('selection').textContent=`${data.status}. Зафиксированный выбор на development: ${data.development_selection.winner||'НЕТ ДОПУСТИМОГО КАНДИДАТА'}. Это не разрешение на PAPER.`;
   el('result').hidden=false;table();
  }catch(e){report=null;el('status').textContent=e.message+' Результаты не подменяются синтетическими.';}
  finally{busy=false;controls();}if(report)detail(0);}
 el('refresh').addEventListener('click',load);el('split').addEventListener('change',()=>{table();detail(0);});el('variant').addEventListener('change',()=>detail(0));el('side').addEventListener('change',()=>detail(0));el('more').addEventListener('click',()=>detail(offset));
 window.addEventListener('pagehide',()=>{stopped=true;generation++;controllers.forEach(c=>c.abort());});
})();

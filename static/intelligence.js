/* Owner-only manual replay; no exchange clients, automatic activation or fabricated metrics. */
(() => {
  'use strict';
  const reasons={NO_EDGE:'Нет подтверждённого преимущества после издержек',INSUFFICIENT_DATA:'Недостаточно исторических аналогов',CONTEXT_UNKNOWN:'Неопределённый рыночный контекст',POSITION_ALREADY_OPEN:'Уже есть виртуальная позиция',LIVE_VALIDATION_REQUIRED:'Live-исполнение отключено: нужна независимая проверка',NO_FRESH_DATA:'Нет свежих данных'};
  const states={PROPOSED:'План ожидает подтверждения',CONFIRMED:'Подтверждён; вход на следующей свече',PAPER_EXECUTED:'Виртуальный вход выполнен',EXPIRED:'План устарел',REJECTED:'План отклонён'};
  const number=v=>v===null||v===undefined?'—':Number.isFinite(Number(v))?Number(v).toLocaleString('ru-RU',{maximumFractionDigits:6}):'—';
  const summary=data=>({reason:reasons[data.analysis.reason]||data.analysis.reason||'Экспериментальный кандидат',state:data.proposal?states[data.proposal.status]||data.proposal.status:'Без плана',canConfirm:!!data.proposal&&data.proposal.status==='PROPOSED',balance:data.portfolio.equity_curve.at(-1).balance,pnl:data.portfolio.metrics.net_profit});
  if(typeof module!=='undefined')module.exports={summary,number,reasons,states};
  if(typeof document==='undefined')return;
  const $=id=>document.getElementById(id);if(!$('ai-load'))return;
  let sid=null,current=null,manifest=null,catalogue=[],busy=false,abort=null,stopped=false;
  function text(id,value){$(id).textContent=String(value);}
  function buttons(){for(const id of ['ai-create','ai-propose','ai-confirm','ai-reject','ai-next','ai-fast','ai-live'])$(id).disabled=busy||stopped; if(!busy){$('ai-confirm').disabled=!current?.proposal||current.proposal.status!=='PROPOSED';$('ai-reject').disabled=$('ai-confirm').disabled;$('ai-next').disabled=!current?.can_advance;$('ai-fast').disabled=$('ai-next').disabled;$('ai-propose').disabled=!sid||!!current?.portfolio.open_position;}}
  async function request(path,body){
    if(busy)return;busy=true;buttons();text('ai-status','Запрос выполняется… подтверждение временно недоступно');abort=new AbortController();
    try{
      const response=await fetch('/api/intelligence'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?{}:{'Content-Type':'application/json','X-Aura-Paper':'local-only'},body:body===undefined?undefined:JSON.stringify(body),signal:abort.signal});
      const data=await response.json();if(!response.ok)throw new Error(data.code||data.detail||'Ошибка сервера');if(stopped)return;
      return data;
    }catch(error){if(!stopped){current=null;text('ai-status','Нет доступного подтверждённого состояния: '+String(error.message));$('ai-confirm').disabled=true;}throw error;}
    finally{busy=false;abort=null;buttons();}
  }
  function list(parent,items){parent.replaceChildren();for(const value of items){const li=document.createElement('li');li.textContent=value;parent.append(li);}}
  function plot(bars,patterns){const svg=$('ai-chart');svg.replaceChildren();if(!bars.length)return;const ns='http://www.w3.org/2000/svg';let low=Math.min(...bars.map(b=>Number(b.low))),high=Math.max(...bars.map(b=>Number(b.high))),range=high-low||1;const y=v=>200-(Number(v)-low)/range*180;
    bars.forEach((b,i)=>{const x=8+i*580/bars.length,color=Number(b.close)>=Number(b.open)?'#42d6b0':'#fa788b';const wick=document.createElementNS(ns,'line');for(const [k,v]of Object.entries({x1:x,x2:x,y1:y(b.high),y2:y(b.low),stroke:color}))wick.setAttribute(k,v);svg.append(wick);const body=document.createElementNS(ns,'rect');for(const[k,v]of Object.entries({x:x-3,y:Math.min(y(b.open),y(b.close)),width:6,height:Math.max(1,Math.abs(y(b.open)-y(b.close))),fill:color}))body.setAttribute(k,v);svg.append(body);});
    if(patterns.length){const marker=document.createElementNS(ns,'circle');marker.setAttribute('cx',8+(bars.length-1)*580/bars.length);marker.setAttribute('cy',y(bars.at(-1).high)-8);marker.setAttribute('r',5);marker.setAttribute('fill','#a295fa');const title=document.createElementNS(ns,'title');title.textContent=patterns.map(p=>p.pattern_id).join(', ');marker.append(title);svg.append(marker);}
    const label=document.createElementNS(ns,'text');label.setAttribute('x',8);label.setAttribute('y',16);label.setAttribute('fill','#c3cde1');label.textContent=patterns.map(p=>p.pattern_id).join(' · ');svg.append(label);
  }
  function render(data){current=data;sid=data.session_id;localStorage.setItem('aura.intelligence.session',sid);const s=summary(data),a=data.analysis;
    text('ai-status',data.mode+' · '+s.state);text('ai-context','Режим: '+a.context.regime+' · '+a.timeframe+' · '+new Date(a.timestamp*1000).toISOString());text('ai-decision','Стратегия: '+a.strategy+' · '+s.reason);
    const e=a.evidence;text('ai-evidence','Аналогов: '+e.count+' · wins/losses: '+e.wins+'/'+e.losses+' · средний net: '+number(e.expectancy_after_costs)+' USDT · нижняя оценка среднего: '+number(e.mean_ci95_lower)+' · частота TP раньше SL: '+number(e.target_before_stop_frequency)+' (не вероятность будущей сделки)');
    list($('ai-patterns'),a.patterns.map(p=>p.pattern_id+' · '+p.status+' · '+(p.direction||'нейтральный')));plot(data.candles,a.patterns);
    text('ai-portfolio','Отдельный replay: баланс '+number(s.balance)+' · equity '+number(data.portfolio.equity_curve.at(-1).equity)+' · realized PnL '+number(s.pnl)+' · закрыто '+data.portfolio.metrics.trades);
    const position=data.portfolio.open_position;text('ai-position',position?'Фактическая '+position.direction+' · entry '+number(position.entry_price)+' · quantity '+number(position.size)+' · SL '+number(position.stop_loss)+' · TP '+number(position.take_profit)+' · unrealized equity−balance '+number(Number(data.portfolio.equity_curve.at(-1).equity)-Number(s.balance)):'Открытых replay-позиций нет');
    const p=data.proposal;if(p){const q=p.estimate;text('ai-plan',p.advice+'\n'+(q.direction==='LONG'?'BUY / LONG':'SELL / SHORT')+' · приблизительный entry '+number(q.entry_price)+' · SL '+number(q.stop_loss)+' · TP '+number(q.take_profit)+' · quantity '+number(q.size)+' · риск '+number(q.risk_usdt)+' USDT · R/R '+number(q.planned_risk_reward)+' · fee '+number(q.entry_fee)+' за вход · комиссия '+number(Number(data.config.fee_bps)/100)+'%/сторону, slippage '+number(Number(data.config.slippage_bps)/100)+'%/fill · историческое среднее для размера '+number(p.expected_net_value)+' USDT (не прогноз) · actual: '+p.actual_fill+' · '+s.state);}else text('ai-plan','Нет предложения сделки. WAIT не разрешает автоматический вход.');
    list($('ai-history'),data.portfolio.trades.slice(-10).map(t=>t.direction+' · entry '+number(t.entry_price)+' → exit '+number(t.exit_price)+' · net '+number(t.realized_pnl)+' · '+t.exit_reason));buttons();
  }
  function catalog(){const search=$('ai-search').value.toLowerCase(),category=$('ai-category').value;list($('ai-catalogue'),catalogue.filter(p=>(!category||p.category===category)&&(p.name_ru+' '+p.name_en).toLowerCase().includes(search)).map(p=>p.name_ru+' / '+p.name_en+' · '+p.category+' · '+p.status+' · '+p.limitations));}
  const action=fn=>async()=>{try{await fn();}catch{}};
  $('ai-load').addEventListener('click',action(async()=>{manifest=await request('/manifest');catalogue=await request('/catalogue');text('ai-source',manifest.source+' · training до '+new Date(manifest.training_end*1000).toISOString()+' · checksum '+manifest.dataset_sha256);$('ai-date').value=new Date(manifest.smoke.candle_time*1000).toISOString().slice(0,16);catalog();const saved=localStorage.getItem('aura.intelligence.session');if(saved)render(await request('/sessions/'+encodeURIComponent(saved)));else text('ai-status','История загружена. Создайте отдельный replay.');}));
  $('ai-create').addEventListener('click',action(async()=>{if(!manifest)throw new Error('Сначала загрузите историю');const timestamp=Date.parse($('ai-date').value+'Z')/1000;render(await request('/sessions',{timeframe:$('ai-timeframe').value,candle_time:timestamp,manual_research:$('ai-manual').checked}));}));
  $('ai-propose').addEventListener('click',action(async()=>{if(!sid)return;render(await request('/sessions/'+sid+'/proposal',{manual:current.analysis.strategy==='WAIT'}));}));
  $('ai-confirm').addEventListener('click',action(async()=>{if(!current?.proposal||!window.confirm('Подтвердить только виртуальный replay-вход? При WAIT это ручной эксперимент без доказанного преимущества. Реальные деньги не используются.'))return;render(await request('/sessions/'+sid+'/decision',{proposal_id:current.proposal.id,confirm:true}));}));
  $('ai-reject').addEventListener('click',action(async()=>{render(await request('/sessions/'+sid+'/decision',{proposal_id:current.proposal.id,confirm:false}));}));
  for(const[id,steps]of[['ai-next',1],['ai-fast',32]])$(id).addEventListener('click',action(async()=>render(await request('/sessions/'+sid+'/advance',{steps}))));
  $('ai-live').addEventListener('click',action(async()=>{const d=await request('/live?timeframe=15m');current=null;sid=null;text('ai-status','Live: '+d.strategy+' · '+(reasons[d.reason]||d.reason)+' · исполнение отключено');text('ai-plan','Live-план отсутствует. Для ручного replay снова откройте вкладку.');buttons();}));
  $('ai-search').addEventListener('input',catalog);$('ai-category').addEventListener('change',catalog);
  window.addEventListener('pagehide',()=>{stopped=true;abort?.abort();buttons();});buttons();
})();

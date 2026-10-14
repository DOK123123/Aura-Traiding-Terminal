/* Owner-only journal reads. No scheduler secret or capture/trading writes. */
(()=>{
 'use strict';
 const numeric=v=>v===null||v===undefined?'—':Number.isFinite(Number(v))?Number(v).toLocaleString('ru-RU',{maximumFractionDigits:4}):'—';
 const date=v=>typeof v==='number'?new Date(v).toLocaleString('ru-RU',{timeZone:'UTC'})+' UTC':'—';
 const labels={SCHEDULER_NOT_CONFIGURED:'Внешний scheduler не настроен',NO_SCHEDULE_OBSERVED:'Запуски ещё не зарегистрированы',LAST_RUN_INCOMPLETE:'Завершение последнего запуска не подтверждено',NO_FRESH_CAPTURES:'Нет свежих записей',RECENT_CAPTURE_OBSERVED:'Недавняя запись зарегистрирована; 24/7 не подтверждено',STORAGE_NOT_CONFIGURED:'Не настроено постоянное хранилище',RENDER_REQUIRES_DURABLE_STORAGE:'Render требует постоянное внешнее хранилище',ARTIFACT_REQUIRED:'Совместимый артефакт 4.0 недоступен',CONFIGURED:'Журнал настроен; непрерывность не гарантируется',FORECAST:'Прогноз записан',ABSTAINED:'WAIT — недостаточно аналогов',COMPLETE:'Исход проверен',MISSING_CANDLES:'Пропуск данных — не оценивается',SOURCE_CORRECTION:'Исправленный источник — не оценивается'};
 function model(data,tf='15m',h=4){
  const monitor=data?.monitoring,c=monitor?.counts||{},stats=data?.statistics;
  const groups=(stats?.groups||[]).filter(x=>x.timeframe===tf&&x.horizon===Number(h)&&x.regime==='ALL');
  const rows=(data?.journal||[]).filter(r=>r.timeframe===tf).map(r=>{const p=r.forecasts?.[h],o=r.outcomes?.[h];return {date:date(r.created_at_ms),tf:r.timeframe,regime:({'TREND_UP':'Восходящий тренд','TREND_DOWN':'Нисходящий тренд','RANGE':'Боковой рынок','UNKNOWN':'Не определено'}[r.regime]||'Не определено'),
   prediction:r.status==='ABSTAINED'?'WAIT':p?numeric(p.mean_return_pct)+'%':'—',actual:o?.quality==='COMPLETE'?numeric(o.return_pct)+'%':'—',
   result:r.corrected?'Есть коррекция; исключён из оценки':o?.quality==='COMPLETE'&&p?'Ошибка '+numeric(Math.abs(Number(o.return_pct)-p.mean_return_pct))+' п.п.':'—',
   status:r.corrected?'Коррекция данных':o?labels[o.quality]||'Ошибка качества':labels[r.status]||'Ожидается исход'};});
  return {status:(labels[data?.collection_state]?labels[data.collection_state]+' · ':'')+(labels[data?.status]||'Проверка недоступна'),capture:date(monitor?.last?.PRED),evaluation:date(monitor?.last_successful_evaluation_ms),
   recorded:monitor?c.PRED||0:null,evaluated:monitor?c.OUTCOME||0:null,pending:monitor?Math.max(0,4*(c.PRED||0)-(c.OUTCOME||0)):null,
   missed:monitor?.missed_closed_candles??null,missedRuns:monitor?.missed_runs??null,
   stale:monitor?.last?.PRED&&data?.server_now_ms-monitor.last.PRED>900000,
   message:!groups.some(g=>g.scores?.aura?.count>0)?'ПРОВЕРКА ЕЩЁ НЕ ЗАВЕРШЕНА':'Описательная оценка; преимущество не установлено',groups,rows};
 }
 function reader(fetcher,onData,onPending){let busy=false,controller=null,closed=false;return {get busy(){return busy;},async read(){
  if(busy||closed)return;busy=true;controller=new AbortController();onPending(true);const timer=setTimeout(()=>controller?.abort(),30000);
  try{const r=await fetcher('/api/intelligence/forward/status',{method:'GET',credentials:'same-origin',cache:'no-store',signal:controller.signal});
   const data=await r.json();if(!closed)onData(data,r.status);
  }catch{if(!closed)onData({status:'UNAVAILABLE'},0);}finally{clearTimeout(timer);busy=false;controller=null;if(!closed)onPending(false);}
 },close(){closed=true;controller?.abort();}};}
 if(typeof module!=='undefined')module.exports={model,reader,numeric,date};
 if(typeof document==='undefined')return;
 const $=id=>document.getElementById(id);if(!$('fv-panel'))return;
 let data=null,failed=false,auth=false;const text=(id,v)=>{$(id).textContent=String(v);};
 function render(){const m=model(data,$('fv-timeframe').value,$('fv-horizon').value);
  text('fv-status',auth?'Требуется вход владельца: aura':(failed?'НЕАКТУАЛЬНО — обновление недоступно. ':'')+(m.stale?'Нет свежих записей. ':'')+m.status);text('fv-times','Последняя запись '+m.capture+' · последняя оценка '+m.evaluation);
  text('fv-counts','Весь журнал: прогнозов '+numeric(m.recorded)+' · проверено наблюдений '+numeric(data?.monitoring?.evaluated_predictions)+' · исходов '+numeric(m.evaluated)+' · ожидается '+numeric(m.pending)+' · пропущено свечей '+numeric(m.missed)+' / запусков '+numeric(m.missedRuns)+' · ошибок данных '+numeric(data?.monitoring?.invalid_outcomes)+' · коррекций '+numeric(data?.monitoring?.counts?.CORRECTION??(data?.monitoring?0:null)));
  text('fv-model','Модель '+(data?.model_version||'—')+' · когорта '+(data?.cohort||'—')+' · хранение '+(data?.backend||'не настроено'));
  text('fv-message',m.message+' · Метрики только текущей когорты, выборка последних 100 прогнозов. Окна пересекаются; эффективное N и доверительные интервалы неизвестны. Это не прибыльность.');
  const scores=[];for(const g of m.groups){scores.push('Покрытие '+numeric(g.prediction_coverage===null?null:g.prediction_coverage*100)+'% · отказ '+numeric(g.abstention_rate===null?null:g.abstention_rate*100)+'% · непересекающихся исходов '+numeric(g.non_overlapping_outcome_count));
   for(const [name,s]of Object.entries(g.scores)){scores.push(({'aura':'Aura','unconditional':'Безусловный baseline','same_regime':'Тот же режим','simple_trend':'Простой тренд','no_change':'Без изменения'}[name]||name)+': n='+s.count+' · MAE '+numeric(s.mae)+' · RMSE '+numeric(s.rmse)+' · точность '+numeric(s.directional_accuracy===null?null:s.directional_accuracy*100)+'% · Brier '+numeric(s.brier)+' · log loss '+(s.log_loss_status==='INFINITY'?'∞':numeric(s.log_loss)));}}
  text('fv-scores',scores.join('\n')||'ПРОВЕРКА ЕЩЁ НЕ ЗАВЕРШЕНА');
  const table=$('fv-journal');table.replaceChildren();for(const r of m.rows.slice(-20).reverse()){const tr=document.createElement('tr');for(const k of ['date','tf','regime','prediction','actual','result','status']){const td=document.createElement('td');td.textContent=r[k];tr.append(td);}table.append(tr);}
 }
 const client=reader(fetch,(value,status)=>{if(status>=200&&status<300){data=value;failed=false;auth=false;render();}else if(status===401||status===403){data=null;auth=true;failed=true;render();}else{failed=true;render();}},pending=>{$('fv-refresh').disabled=pending;$('fv-panel').setAttribute('aria-busy',String(pending));text('fv-loading',pending?'Загрузка журнала…':'');});
 $('fv-refresh').addEventListener('click',()=>client.read());
 $('fv-panel').addEventListener('toggle',()=>{if($('fv-panel').open)client.read();});
 for(const id of ['fv-timeframe','fv-horizon'])$(id).addEventListener('change',render);
 const interval=setInterval(()=>{if($('fv-panel').open&&!document.hidden)client.read();},60000);
 window.addEventListener('pagehide',()=>{client.close();clearInterval(interval);});render();
})();

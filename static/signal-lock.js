/* Read-only locked-event view. Activation requires a configured durable backend. */
(function(root){'use strict';
 const LABELS={CANDIDATE:'Предварительный кандидат',WATCH:'Технический сценарий',
  EXPIRED:'Срок истёк',INVALIDATED:'Условия отмены выполнены',UNKNOWN:'Данные не подтверждены'};
 function visible(event,now){
  const copy=structuredClone(event);
  if(!['EXPIRED','INVALIDATED'].includes(copy.status)){
   if(now>=copy.valid_until)copy.status='EXPIRED';
   else if(!Number.isFinite(now)||!Number.isFinite(copy.last_seen)||now-copy.last_seen<0||now-copy.last_seen>5)copy.status='UNKNOWN';
  }
  if(copy.status!=='WATCH')copy.plan=null;
  return copy;
 }
 class Selection{
  constructor(){this.selected=null;this.events=[];this.newCount=0;}
  update(events){this.newCount+=events.filter(e=>!this.events.some(old=>old.id===e.id)).length;
   this.events=events; // Reading selection never follows newer ticks/events.
   if(!this.selected&&events.length)this.selected=events[0].id;
  }
  choose(id){if(this.events.some(e=>e.id===id)){this.selected=id;this.newCount=0;}}
  current(now){const row=this.events.find(e=>e.id===this.selected);return row?visible(row,now):null;}
 }
 // Deliberately not auto-mounted: durable storage and notification activation
 // have an owner configuration gate. This view accepts server events only.
 function mount(host,{storage=localStorage,now=()=>Date.now()/1000}={}){
  const model=new Selection(),key='aura.signal-lock.view.v1';
  let saved={};try{saved=JSON.parse(storage.getItem(key))||{};}catch{}
  let frame=['5m','15m','1h','4h'].includes(saved.frame)?saved.frame:'15m';
  const selected=saved.selected&&typeof saved.selected==='object'?saved.selected:{};
  host.classList.add('signal-lock');
  host.innerHTML='<header><strong>BTCUSDT</strong> <span data-quote>— · UNKNOWN</span></header>'+
   '<nav aria-label="Таймфрейм"></nav><button data-new hidden></button>'+
   '<article><h2 data-heading>Нет зафиксированного события</h2><p data-status></p>'+
   '<p data-time></p><p data-score></p><dl data-plan hidden></dl>'+
   '<details><summary>Открыть подробности</summary><p data-reasons></p>'+ 
   '<p>Технический балл не является вероятностью прибыли. Торговые действия не выполняются.</p></details></article>'+
   '<label>История <select aria-label="Фильтр истории"><option value="">Все статусы</option>'+
   Object.keys(LABELS).map(s=>'<option value="'+s+'">'+s+'</option>').join('')+
   '</select></label><div data-history></div>';
  const get=s=>host.querySelector(s),details=get('details');let all=[],historySignature='';
  details.open=saved.details===true;
  function persist(){try{storage.setItem(key,JSON.stringify({frame,selected,details:details.open}));}catch{}}
  details.addEventListener('toggle',persist);
  for(const tf of ['5m','15m','1h','4h']){
   const b=document.createElement('button');b.textContent=tf;b.dataset.frame=tf;
   b.onclick=()=>{frame=tf;model.selected=selected[frame]||null;model.events=[];model.newCount=0;refresh();persist();};
   get('nav').append(b);
  }
  const names={TREND_PULLBACK:'Откат по тренду',BREAKOUT_RETEST:'Пробой и ретест',MOMENTUM_DIVERGENCE:'Дивергенция импульса'};
  const fmt=t=>Number.isFinite(t)?new Date(t*1000).toLocaleString('ru-RU'):'Время не подтверждено';
  function render(){
   const row=model.current(now());
   get('[data-heading]').textContent=row?row.direction+' · '+row.frame+' · '+(names[row.strategy]||'Стратегия'):'Нет зафиксированного события';
   get('[data-status]').textContent=row?(LABELS[row.status]||LABELS.UNKNOWN):'Ожидание достоверных данных';
   get('[data-time]').textContent=row?'Обнаружен '+fmt(row.detected_at)+' · до '+fmt(row.valid_until):'';
   get('[data-score]').textContent=row&&row.status==='CANDIDATE'?'Технический балл '+row.score+'/100 · не вероятность прибыли':'';
   const plan=get('[data-plan]');plan.hidden=!row?.plan;
   if(row?.plan){
    if(!plan.children.length)for(const label of ['Entry','Stop Loss','Take Profit','Net R/R','Риск USDT на 1 BTC']){
     const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;plan.append(dt,dd);
    }
    ['entry','sl','tp','net_rr','risk_usdt_per_btc'].forEach((k,i)=>plan.querySelectorAll('dd')[i].textContent=Number.isFinite(row.plan[k])?row.plan[k].toFixed(2):'Нет расчёта');
   }
   get('[data-reasons]').textContent=row?(row.missing?.length?'Не выполнено обязательных условий: '+row.missing.length+'. Сценарий требует подтверждения.':
    row.status==='WATCH'?'Обязательные технические условия выполнены. Прибыльность не подтверждена.':LABELS[row.status]):'Данные отсутствуют';
   get('[data-new]').hidden=model.newCount===0;get('[data-new]').textContent='Новых событий: '+model.newCount+' · открыть последнее';
   host.querySelectorAll('[data-frame]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.frame===frame)));
   const filter=get('select').value,rows=model.events.filter(e=>!filter||visible(e,now()).status===filter);
   const signature=JSON.stringify(rows.map(e=>[e.id,visible(e,now()).status]));
   if(signature!==historySignature){historySignature=signature;get('[data-history]').replaceChildren(...rows.map(e=>{
    const b=document.createElement('button');b.textContent=e.direction+' · '+e.frame+' · '+visible(e,now()).status+' · '+fmt(e.detected_at);
    b.onclick=()=>{model.choose(e.id);selected[frame]=e.id;persist();render();};return b;
   }));}
  }
  function refresh(){model.update(all.filter(e=>e.frame===frame));if(selected[frame])model.selected=selected[frame];
   else if(model.selected)selected[frame]=model.selected;render();persist();}
  get('select').onchange=render;
  get('[data-new]').onclick=()=>{const event=model.events[0];if(event){model.choose(event.id);selected[frame]=event.id;persist();render();}};
  return {update(events){all=events.slice().sort((a,b)=>b.detected_at-a.detected_at);refresh();},
   quote(text){get('[data-quote]').textContent=text;},tick:render,selection:()=>model.selected,frame:()=>frame};
 }
 const api={visible,Selection,LABELS,mount};root.AuraSignalLock=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);

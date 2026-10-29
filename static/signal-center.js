(function(){'use strict';if(document.body.dataset.manualPreview!=='true')return;
const E=window.AuraManualStrategies,F=window.AuraForwardObserver,host=document.getElementById('aura-signal-center');if(!E||!F||!host)return;
const title=document.createElement('h2');title.textContent='AURA · РУЧНЫЕ СЦЕНАРИИ';host.append(title);
const warning=document.createElement('p');warning.textContent='NO_VALIDATED_EDGE · UNVALIDATED. Технический LONG/SHORT не означает доказанную прибыльность. Расходы модельные; funding не учтён. Observer работает только в открытой вкладке, разрывы учитывает как UNOBSERVED. Виртуальная сделка требует отдельного подтверждения.';host.append(warning);
const controls=document.createElement('div'),cards=document.createElement('div'),log=document.createElement('details'),summary=document.createElement('summary'),history=document.createElement('ol'),state=document.createElement('p');cards.className='signal-cards';summary.textContent='Forward observer · локальная история (не сделки)';log.append(summary,history);host.append(controls,state,cards,log);
const enabled=new Set(Object.keys(E.names));let storage=null;try{storage=localStorage;}catch{}
const observer=new F.Observer(storage);window.AuraManualForwardObserver=observer;let latest=null,last=0;
for(const [id,name]of Object.entries(E.names)){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=true;input.addEventListener('change',()=>{if(input.checked)enabled.add(id);else enabled.delete(id);last=0;if(latest)render(latest,Date.now()/1000);});label.append(input,document.createTextNode(name+' '));controls.append(label);}
const exportButton=document.createElement('button');exportButton.type='button';exportButton.textContent='Скачать журнал observer';exportButton.addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify({version:F.VERSION,items:observer.items},null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='aura-forward-observer.json';a.click();URL.revokeObjectURL(url);});log.append(exportButton);
function renderHistory(){history.replaceChildren();for(const x of observer.items.slice(-100).reverse()){const li=document.createElement('li');li.textContent=new Date(x.detected_at*1000).toISOString()+' · '+x.strategy+' '+x.tf+' '+x.side+' · '+x.outcome+' · '+(x.pnl_fraction===null?'исход не определён':(100*x.pnl_fraction).toFixed(3)+'% после расходов');history.append(li);}}
function render(snapshot,now){
 const rows=E.analyze(snapshot,now),visible=rows.filter(x=>enabled.has(x.strategy));observer.update(snapshot,rows,now);cards.replaceChildren();
 state.textContent='NO_VALIDATED_EDGE · '+(snapshot.status==='LIVE'?'Свежесть проверяется отдельно для каждой стратегии':'STALE · вход заблокирован')+(observer.error?' · '+observer.error:'');
 let selected=null;
 for(const x of visible){
  const card=document.createElement('article'),h=document.createElement('h3'),p=document.createElement('p');h.textContent=x.name+' · '+x.tf+' · '+x.state+' · '+x.edge;p.textContent=[...x.reasons,...x.rejection].join('; ');card.append(h,p);
  const meta=document.createElement('p');meta.textContent=(x.fresh?'Данные свежие':'Данные НЕАКТУАЛЬНЫ')+' · '+(x.technical_strength||'Нет подтверждения')+' · возраст котировки '+(Number.isFinite(x.quote_age)?x.quote_age.toFixed(1)+' с':'—');card.append(meta);
  if(x.zone){const details=document.createElement('p');details.textContent='Entry '+x.entry.toFixed(2)+' · зона '+x.zone.low.toFixed(2)+'–'+x.zone.high.toFixed(2)+' · SL '+x.stop.toFixed(2)+' · TP '+x.target.toFixed(2)+' · net R/R '+(x.net_rr?.toFixed(2)||'—')+' · до '+new Date(x.valid_until*1000).toISOString()+'. Отмена: '+x.cancel;card.append(details);}
  if(['LONG','SHORT'].includes(x.state)){
   const copy=document.createElement('button');copy.type='button';copy.textContent='Перенести '+x.setup+' в ручную форму · без сделки';
   copy.addEventListener('click',()=>{
    const current=E.analyze(latest,Date.now()/1000).find(v=>v.id===x.id);
    if(!current||!['LONG','SHORT'].includes(current.state))return;
    const fields=['entry','stop','target'].map(k=>document.getElementById('mp-'+k));
    if(fields.some(f=>!f||f.disabled))return;
    fields.forEach((f,i)=>{f.value=current[['entry','stop','target'][i]].toFixed(1);});
    document.getElementById('manual-paper-panel').open=true;
    document.getElementById('mp-status').textContent='План '+current.setup+' · '+current.name+'. Проверьте объём и подтвердите BUY/SELL отдельно. Сделка не создана.';
   });card.append(copy);
  }
  if(!selected&&['LONG','SHORT'].includes(x.state)&&x.tf===(document.querySelector('#timeframes button.active')?.dataset.tf||'15m'))selected=x;
  cards.append(card);
 }
 window.dispatchEvent(new CustomEvent('aura-manual-scenario',{detail:selected}));renderHistory();
}
renderHistory();window.addEventListener('aura-manual-market',e=>{latest=e.detail;const now=Date.now()/1000;if(now-last<1&&latest.status==='LIVE')return;last=now;render(latest,now);});
// Independently expire cards/lines if the producer stops publishing events.
setInterval(()=>{if(latest&&Date.now()/1000-last>=2){last=Date.now()/1000;render(latest,last);}},1000);
})();

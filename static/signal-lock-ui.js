/* Server-owned Aura 5 episodes. No order/ledger endpoints. */
(function(root){'use strict';
const KEY='aura5.server-lock.selection.v1',STATES=['CANDIDATE','WATCH','INVALIDATED','EXPIRED','UNKNOWN'];
function current(row,data,now){if(!row||!STATES.includes(row.status))return 'UNKNOWN';if(!['CANDIDATE','WATCH'].includes(row.status))return row.status;
 if(![now,data.server_time,data.updated_at,row.refreshed_at,row.valid_until].every(Number.isFinite)||data.error||Math.abs(now-data.server_time)>5||now-data.updated_at>5||now-row.refreshed_at>5||now<row.refreshed_at)return 'UNKNOWN';return now>=row.valid_until?'EXPIRED':row.status;}
root.Aura5SignalLock={current};if(typeof module!=='undefined')module.exports=root.Aura5SignalLock;
if(!root.document)return;
const host=document.getElementById('aura-explainable');if(!host||!document.querySelector('meta[name="aura5-server-lock"]'))return;
const add=(tag,parent,text='')=>{const e=document.createElement(tag);e.textContent=text;parent.append(e);return e;};
const panel=add('section',host);panel.className='server-lock';panel.hidden=true;add('h2',panel,'Aura 5 · Signal Lock');
add('p',panel,'NO_EDGE_FOUND · Технический балл — не вероятность прибыли. Сделки не выполняются.');
if(document.querySelector('meta[name="aura5-server-lock"]')){for(const e of [...host.children])if(e!==panel)e.hidden=true;panel.hidden=false;host.classList.add('server-lock-active');}
const market=add('p',panel);const badge=add('p',panel);badge.setAttribute('role','status');let activated=false,data=null,revision='',seen=new Set(),count=0,selection={};
try{const saved=JSON.parse(localStorage.getItem(KEY)||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))selection=Object.fromEntries(Object.entries(saved).filter(([k,v])=>['LONG','SHORT'].includes(k)&&/^[a-f0-9]{64}$/.test(v)));}catch{}
const pinKey='aura5.server-lock.pins.v1';let pins={};try{const saved=JSON.parse(localStorage.getItem(pinKey)||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))pins=saved;}catch{}
const link=new URL(location.href).searchParams.get('scenario');let linkApplied=false;
const detailKey='aura5.server-lock.details.v1';let detailState={};try{const saved=JSON.parse(localStorage.getItem(detailKey)||'{}');if(saved&&typeof saved==='object')detailState=saved;}catch{}
const slots=['LONG','SHORT'].map(side=>{const card=add('article',panel);card.dataset.side=side;const title=add('h3',card),select=add('select',card);select.setAttribute('aria-label','Выбрать сценарий '+side);
 const meta=add('p',card),missing=add('p',card),plan=add('p',card),pin=add('button',card,'Закрепить чтение'),detail=add('details',card);pin.type='button';add('summary',detail,'Условия и история переходов');detail.open=detailState[side]===true;detail.addEventListener('toggle',()=>{detailState[side]=detail.open;try{localStorage.setItem(detailKey,JSON.stringify(detailState));}catch{}});const body=add('pre',detail);body.style.whiteSpace='pre-wrap';
 let pinned=pins[side]===true;pin.setAttribute('aria-pressed',String(pinned));pin.textContent=pinned?'Открепить чтение':'Закрепить чтение';card.dataset.pinned=String(pinned);pin.onclick=()=>{pinned=!pinned;pins[side]=pinned;card.dataset.pinned=String(pinned);pin.setAttribute('aria-pressed',String(pinned));pin.textContent=pinned?'Открепить чтение':'Закрепить чтение';try{localStorage.setItem(pinKey,JSON.stringify(pins));localStorage.setItem(KEY,JSON.stringify(selection));}catch{}};
 select.onchange=()=>{selection[side]=select.value;count=0;try{localStorage.setItem(KEY,JSON.stringify(selection));}catch{}paint();};
 return {side,card,title,select,meta,missing,plan,body,signature:''};});
const historyMount=document.querySelector('#app-more .aura-more-card')||panel;
const history=add('details',historyMount);add('summary',history,'Серверная история · все статусы');const journal=add('ol',history);
const text=(e,t)=>{if(e.textContent!==t)e.textContent=t;};const date=n=>Number.isFinite(n)?new Date(n*1000).toISOString():'—';
function paint(){if(!data)return;const now=Date.now()/1000;const q=Object.values(data.quotes||{})[0];text(market,q&&!data.error&&now-q.time<=5&&now-q.received_at<=5?'BTCUSDT · Bid '+q.bid+' / Ask '+q.ask+' · возраст '+(now-q.time).toFixed(1)+' с':'UNKNOWN · свежая котировка не подтверждена');for(const s of slots){const rows=data.records.filter(r=>r.direction===s.side),signature=rows.map(r=>r.id).join('|');
 if(signature!==s.signature){s.signature=signature;s.select.replaceChildren();for(const r of rows){const o=add('option',s.select,r.strategy+' · '+r.frame+' · '+date(r.detected_at));o.value=r.id;}}
 if(!selection[s.side]&&rows.length){selection[s.side]=rows[0].id;try{localStorage.setItem(KEY,JSON.stringify(selection));}catch{}}
 if(link&&!linkApplied){const r=rows.find(r=>r.id===link);if(r){selection[s.side]=r.id;linkApplied=true;document.getElementById('app-tab-signals')?.click();}}
 const r=rows.find(r=>r.id===selection[s.side]);s.select.value=r?.id||'';
 if(!r){text(s.title,s.side+' · Нет зафиксированных сценариев');text(s.plan,'');continue;}
 const state=current(r,data,now);s.card.dataset.scenarioId=r.id;s.card.dataset.state=state;
 text(s.title,s.side+' · '+r.strategy+' · '+r.frame+' · '+state);
 text(s.meta,'Технический балл '+r.score+'/100 · обнаружен '+date(r.detected_at)+' · ID '+r.id);
 text(s.missing,state==='CANDIDATE'?'Не выполнено: '+(r.missing||[]).join(', '):'');
 const p=r.current_plan;text(s.plan,state==='WATCH'&&p?'Entry '+p.entry+' · SL '+p.sl+' · TP '+p.tp+' · Net R/R '+p.net_rr:'Действующий план отсутствует. Прошлые уровни — только в истории.');
 text(s.body,'Подтверждение: '+(r.initial.confirmation||'Все обязательные условия')+'\nОтмена: '+(r.initial.cancel||'Нарушение условий, свежести или срока')+'\n'+r.history.map(e=>date(e.at)+' · '+e.to+' · '+e.reason+(e.plan?' · исторический план '+JSON.stringify(e.plan):'')).join('\n'));
 }
 text(badge,(data.error?'Данные недоступны · UNKNOWN. ':'')+(count?'Новых событий: '+count+' · выберите сценарий вручную.':'Выбранная карточка не заменяется новыми событиями.'));
 const sig=data.records.map(r=>r.id+':'+r.revision).join('|');if(sig!==revision){revision=sig;journal.replaceChildren();for(const r of data.records)for(const e of r.history||[])add('li',journal,date(e.at)+' · '+r.direction+' '+r.strategy+' '+r.frame+' · '+e.to);}
}
async function poll(){try{const r=await fetch('/api/preview/signals/locked?selected='+encodeURIComponent([...new Set([...Object.values(selection),link].filter(x=>/^[a-f0-9]{64}$/.test(x||'')))].slice(0,3).join(',')),{credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error();const v=await r.json();if(v.scope!=='AURA5_SIGNAL_LOCK_V1'||!Array.isArray(v.records)||v.exchange_execution!==false)throw Error();
 if(!activated){activated=true;if(historyMount!==panel){const note=historyMount.querySelector('p.aura-subtle');if(note)note.textContent='Серверная история Signal Lock в Supabase · не история сделок.';document.querySelectorAll('.explain-history').forEach(e=>e.hidden=true);}for(const e of [...host.children])if(e!==panel)e.hidden=true;panel.hidden=false;host.classList.add('server-lock-active');}
 for(const row of v.records)for(const e of row.history||[]){if(!seen.has(e.id)){if(data)count++;seen.add(e.id);}}
 data=v;paint();
 }catch{if(!data){text(badge,'Signal Lock недоступен · UNKNOWN. Действующего плана нет.');}if(data){data={...data,error:'CONNECTION_UNAVAILABLE'};paint();}}finally{setTimeout(poll,1500);}}
setInterval(paint,500);void poll();
})(typeof window==='undefined'?globalThis:window);

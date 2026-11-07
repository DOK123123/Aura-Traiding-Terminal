/* Server-owned Aura 5 episodes. No order/ledger endpoints. */
(function(root){'use strict';
const KEY='aura5.server-lock.selection.v1',STATES=['CANDIDATE','WATCH','INVALIDATED','EXPIRED','UNKNOWN'];
const ACTIVE=['WATCH','CANDIDATE'],FRAMES=['5m','15m','1h','4h'];
function current(row,data,now){if(!row||!STATES.includes(row.status))return 'UNKNOWN';if(!ACTIVE.includes(row.status))return row.status;
 if(![now,data.server_time,data.updated_at,row.refreshed_at,row.valid_until].every(Number.isFinite)||data.error||Math.abs(now-data.server_time)>5||now-data.updated_at>5||now<data.updated_at||now-row.refreshed_at>5||now<row.refreshed_at)return 'UNKNOWN';return now>=row.valid_until?'EXPIRED':row.status;}
function ranked(records,side,data,now){return records.filter(r=>r&&r.direction===side&&typeof r.id==='string').slice().sort((a,b)=>{
 const rank=r=>({WATCH:0,CANDIDATE:1}[current(r,data,now)]??2);return rank(a)-rank(b)||(b.detected_at||0)-(a.detected_at||0)||a.id.localeCompare(b.id);});}
function choose(rows,id,pinned,data,now){const selected=rows.find(r=>r.id===id);if(pinned)return selected||null;
 return selected&&ACTIVE.includes(current(selected,data,now))?selected:rows.find(r=>ACTIVE.includes(current(r,data,now)))||null;}
function scoreChecks(row){return Array.isArray(row.current_checks)?row.current_checks.filter(x=>x&&typeof x.code==='string'):[];}
root.Aura5SignalLock={current,ranked,choose,scoreChecks};if(typeof module!=='undefined')module.exports=root.Aura5SignalLock;
if(!root.document)return;
const host=document.getElementById('aura-explainable');if(!host||!document.querySelector('meta[name="aura5-server-lock"]'))return;
const add=(tag,parent,text='')=>{const e=document.createElement(tag);e.textContent=text;parent.append(e);return e;};
const panel=add('section',host);panel.className='server-lock';panel.hidden=true;add('h2',panel,'Aura 5 · Signal Lock');
add('p',panel,'NO_EDGE_FOUND · Технический балл — доля условий, не вероятность прибыли. Даже 100/100 не заменяет проверки WATCH и риска. Сделки не выполняются.');
for(const e of [...host.children])if(e!==panel)e.hidden=true;panel.hidden=false;host.classList.add('server-lock-active');
const market=add('p',panel),regimeBox=add('section',panel);regimeBox.className='market-regimes';add('h3',regimeBox,'Состояние рынка · закрытые свечи');
const regimeNodes=Object.fromEntries(FRAMES.map(frame=>[frame,add('p',regimeBox,frame+' · UNKNOWN')]));
const regimeDetails=add('details',regimeBox);add('summary',regimeDetails,'Правила классификации · техническое описание, не прогноз');
add('p',regimeDetails,'Только 260 закрытых свечей. ADX14 ≥25: сильное направленное движение; ≤20: слабое; между ними — переходная зона. TREND требует согласованных EMA20/50, наклона EMA20 за 5 свечей >0.1 ATR на свечу, high/low двух закрытых 10-свечных блоков и эффективности движения за 20 свечей ≥0.3. RANGE требует ADX≤20, плоского наклона, эффективности <0.3, смешанной структуры и цены внутри прежнего диапазона. Противоречия → TRANSITION, недостоверные данные → UNKNOWN. Пороги фиксированы и не являются статистическим доказательством преимущества.');
const badge=add('p',panel);badge.setAttribute('role','status');let activated=false,data=null,revision='',seen=new Set(),count=0,selection={};
try{const saved=JSON.parse(localStorage.getItem(KEY)||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))selection=Object.fromEntries(Object.entries(saved).filter(([k,v])=>['LONG','SHORT'].includes(k)&&/^[a-f0-9]{64}$/.test(v)));}catch{}
const pinKey='aura5.server-lock.pins.v1';let pins={};try{const saved=JSON.parse(localStorage.getItem(pinKey)||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))pins=saved;}catch{}
const link=new URL(location.href).searchParams.get('scenario');let linkApplied=false;
const detailKey='aura5.server-lock.details.v1';let detailState={};try{const saved=JSON.parse(localStorage.getItem(detailKey)||'{}');if(saved&&typeof saved==='object')detailState=saved;}catch{}
function save(){try{localStorage.setItem(KEY,JSON.stringify(selection));localStorage.setItem(pinKey,JSON.stringify(pins));}catch{}}
const labels={EMA_TREND:'Направление EMA20/50',TREND_STRUCTURE:'Структура HH/HL или LH/LL',PULLBACK:'Возврат к EMA',RSI:'Диапазон RSI',PRIOR_LEVEL_BREAK:'Пробой заранее известного уровня',LEVEL_HELD:'Уровень удержан',SEPARATE_RETEST:'Отдельный ретест',BREAK_VOLUME:'Объём пробоя',CONFIRMED_PIVOTS:'Подтверждённые экстремумы',PRICE_DIVERGENCE:'Дивергенция цены',RSI_DIVERGENCE:'Дивергенция RSI',MACD_DIVERGENCE:'Дивергенция MACD',MOMENTUM_TURN:'Разворот импульса',CLOSED_CANDLE_CONFIRMATION:'Подтверждающая закрытая свеча'};
const reasons={UNKNOWN:'Нет свежего достоверного подтверждения',EXPIRED:'Срок сценария истёк',INVALIDATED:'Сценарий отменён',UNKNOWN_NO_CURRENT_PLAN:'Нет текущего плана без свежих данных',EXPIRED_NO_CURRENT_PLAN:'Срок текущего плана истёк',STRUCTURE_REPLACED:'Сменилась закрытая рыночная структура',LOCKED_PLAN_LEVEL_REACHED:'Достигнут уровень SL или TP закреплённого плана',REGIME_RANGE_TREND_RESTRICTED:'RANGE: трендовый сценарий ограничен',MISSING_MANDATORY_CONDITIONS:'Не выполнены обязательные условия',MANDATORY_CONDITION_LOST:'Утрачены условия или структура',UNTRUSTED_OR_STALE_DATA:'Нет достоверных свежих данных',DEADLINE_REACHED:'Истёк срок сценария',NO_VALID_RISK_PLAN:'Нет корректного плана с допустимым Net R/R',NET_RR_BELOW_1_5_OR_INVALID_GEOMETRY:'Net R/R ниже 1.5 или неверная геометрия',NO_KNOWN_OPPOSING_PIVOT_TARGET:'Нет известного встречного уровня для TP',STOP_WIDER_THAN_3_ATR:'SL шире 3 ATR',OUTSIDE_CLOSED_SIGNAL_ENTRY_ZONE:'Цена вне допустимой зоны входа',ENTRY_IN_OPPOSING_ZONE:'Цена во встречной зоне',TARGET_TOO_FAR_FOR_HORIZON:'Цель слишком далека для горизонта',NO_STRUCTURAL_INVALIDATION_BEHIND_ENTRY:'Нет структурного уровня отмены за входом'};
const explain=code=>reasons[code]||labels[code]||code;
const slots=['LONG','SHORT'].map(side=>{const card=add('article',panel);card.dataset.side=side;const title=add('h3',card),select=add('select',card);select.setAttribute('aria-label','Выбрать сценарий '+side);
 const meta=add('p',card),missing=add('p',card),plan=add('p',card),pin=add('button',card,'Закрепить чтение'),detail=add('details',card);pin.type='button';add('summary',detail,'Условия и история переходов');detail.open=detailState[side]===true;detail.addEventListener('toggle',()=>{detailState[side]=detail.open;try{localStorage.setItem(detailKey,JSON.stringify(detailState));}catch{}});
 const conditions=add('ul',detail),body=add('pre',detail);body.style.whiteSpace='pre-wrap';
 pin.onclick=()=>{pins[side]=!pins[side];save();paint();};
 select.onchange=()=>{selection[side]=select.value;const row=data?.records.find(r=>r.id===select.value);if(row&&!ACTIVE.includes(current(row,data,Date.now()/1000)))pins[side]=true;count=0;save();paint();};
 return {side,card,title,select,meta,missing,plan,pin,conditions,body,signature:'',checksSignature:''};});
const historyMount=document.querySelector('#app-more .aura-more-card')||panel;
const history=add('details',historyMount);add('summary',history,'Серверная история · все статусы');const journal=add('ol',history);
const text=(e,t)=>{if(e.textContent!==t)e.textContent=t;};const date=n=>Number.isFinite(n)?new Date(n*1000).toISOString():'—';
const num=n=>Number.isFinite(n)?n.toLocaleString('ru-RU',{maximumFractionDigits:3}):'—';
function paint(){if(!data)return;const now=Date.now()/1000,q=Object.values(data.quotes||{})[0];
 const quoteOk=q&&!data.error&&[q.bid,q.ask,q.time,q.received_at].every(Number.isFinite)&&q.bid>0&&q.ask>=q.bid&&now>=q.time&&now-q.time<=5&&now>=q.received_at&&now-q.received_at<=5;
 text(market,quoteOk?'BTCUSDT · Bid '+q.bid+' / Ask '+q.ask+' · возраст '+(now-q.time).toFixed(1)+' с':'UNKNOWN · свежая котировка не подтверждена');
 for(const frame of FRAMES){const regime=data.market_regimes?.[frame],m=regime?.metrics,step={'5m':300,'15m':900,'1h':3600,'4h':14400}[frame],usable=quoteOk&&Number.isFinite(data.server_time)&&Math.abs(now-data.server_time)<=5&&0<=now-data.updated_at&&now-data.updated_at<=5&&regime?.closed_at===Math.floor(now/step)*step;
  const state=usable&&['TREND_UP','TREND_DOWN','RANGE','TRANSITION'].includes(regime?.state)?regime.state:'UNKNOWN';
  text(regimeNodes[frame],frame+' · '+state+(state!=='UNKNOWN'&&m?' · ADX14 '+num(m.adx14)+' · ATR14 '+num(m.atr14)+' · наклон EMA/ATR '+num(m.ema_slope_atr_per_bar)+' · '+m.structure+' · диапазон '+num(m.range_low)+'–'+num(m.range_high):' · нет свежей подтверждённой классификации'));
 }
 for(const s of slots){const rows=ranked(data.records,s.side,data,now);
  if(link&&!linkApplied){const row=rows.find(r=>r.id===link);if(row){selection[s.side]=row.id;pins[s.side]=true;linkApplied=true;save();document.getElementById('app-tab-signals')?.click();}}
  const r=choose(rows,selection[s.side],pins[s.side]===true,data,now);selection[s.side]=r?.id||'';
  const signature=rows.map(r=>r.id+':'+current(r,data,now)).join('|');
  if(signature!==s.signature){s.signature=signature;s.select.replaceChildren();const empty=add('option',s.select,'Текущий сценарий отсутствует · история ниже');empty.value='';for(const row of rows){const o=add('option',s.select,current(row,data,now)+' · '+row.strategy+' · '+row.frame+' · '+date(row.detected_at));o.value=row.id;}}
  s.select.value=r?.id||'';s.pin.disabled=!r;s.card.dataset.pinned=String(pins[s.side]===true);s.pin.setAttribute('aria-pressed',String(pins[s.side]===true));text(s.pin,pins[s.side]?'Открепить чтение':'Закрепить чтение');
  if(!r){s.card.dataset.scenarioId='';s.card.dataset.state='NONE';text(s.title,s.side+' · Нет текущего сценария');text(s.meta,'Старые UNKNOWN / EXPIRED / INVALIDATED доступны в истории и списке выбора.');text(s.missing,'Новый сценарий должен пройти обязательные проверки.');text(s.plan,'Entry / SL / TP отсутствуют: нет текущего сценария.');text(s.body,'');if(s.checksSignature!=='EMPTY'){s.conditions.replaceChildren();s.checksSignature='EMPTY';}continue;}
  const state=current(r,data,now),checks=scoreChecks(r),passed=checks.filter(x=>x.passed===true).length;
  s.card.dataset.scenarioId=r.id;s.card.dataset.state=state;
  text(s.title,s.side+' · '+r.strategy+' · '+r.frame+' · '+state+(pins[s.side]?' · закреплено для чтения':''));
  const why=checks.length?' · '+passed+' из '+checks.length+' равновесных условий, округление':' · текущая разбивка недоступна в старой записи';
  text(s.meta,(ACTIVE.includes(state)?'Технический балл ':'Исторический балл ')+num(r.score)+'/100'+why+' · не вероятность прибыли · обнаружен '+date(r.detected_at)+' · последняя проверка '+date(r.last_evaluated_at)+' · последнее подтверждение WATCH '+date(r.last_confirmed_at)+' · ID '+r.id);
  text(s.missing,state==='CANDIDATE'?'Не выполнено: '+(r.missing||[]).map(explain).join('; '):'');
  const p=r.current_plan;const absence=ACTIVE.includes(state)?r.plan_absence_reasons||r.missing||[]:[...new Set([state,...(r.plan_absence_reasons||[])])];
  text(s.plan,state==='WATCH'&&p?'WATCH — технический сценарий без подтверждённой статистической эффективности. Entry '+p.entry+' · SL '+p.sl+' · TP '+p.tp+' · Net R/R '+p.net_rr:'Entry / SL / TP отсутствуют: '+(absence.length?absence.map(explain).join('; '):'нет проверенного плана')+'. Прошлые уровни — только в истории.');
  const conditionSignature=JSON.stringify(checks);
  if(conditionSignature!==s.checksSignature){s.checksSignature=conditionSignature;s.conditions.replaceChildren();for(const check of checks){const possible=Number.isFinite(check.max_points)?check.max_points:100/checks.length,points=check.passed===true?possible:0;
   add('li',s.conditions,(check.passed===true?'✓ ':'✗ ')+(labels[check.code]||check.code)+' · вклад '+num(points)+' из '+num(possible)+' баллов · вес 1 · требуется: '+String(check.required??'—')+' · факт: '+JSON.stringify(check.actual??null));}}
  text(s.body,'Подтверждение: '+(r.initial?.confirmation||'Все обязательные условия и риск')+'\nОтмена: '+(r.initial?.cancel||'Нарушение условий, свежести или срока')+'\n'+(r.history||[]).map(e=>date(e.at)+' · '+e.to+' · '+explain(e.reason)+(e.plan?' · исторический план '+JSON.stringify(e.plan):'')).join('\n'));
 }
 save();text(badge,(data.error?'Данные недоступны · UNKNOWN. ':'')+'Новых событий: '+count+' · текущие WATCH / CANDIDATE первыми. Закреплённая история сохранена.');
 const sig=data.records.map(r=>r.id+':'+r.revision).join('|');if(sig!==revision){revision=sig;journal.replaceChildren();for(const r of data.records)for(const e of r.history||[])add('li',journal,date(e.at)+' · '+r.direction+' '+r.strategy+' '+r.frame+' · '+e.to);}
}
async function poll(){try{const r=await fetch('/api/preview/signals/locked?selected='+encodeURIComponent([...new Set([...Object.values(selection),link].filter(x=>/^[a-f0-9]{64}$/.test(x||'')))].slice(0,3).join(',')),{credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error();const v=await r.json();if(v.scope!=='AURA5_SIGNAL_LOCK_V1'||!Array.isArray(v.records)||v.exchange_execution!==false)throw Error();
 if(!activated){activated=true;if(historyMount!==panel){const note=historyMount.querySelector('p.aura-subtle');if(note)note.textContent='Серверная история Signal Lock в Supabase · не история сделок.';document.querySelectorAll('.explain-history').forEach(e=>e.hidden=true);}for(const e of [...host.children])if(e!==panel)e.hidden=true;panel.hidden=false;host.classList.add('server-lock-active');}
 for(const row of v.records)for(const e of row.history||[]){if(!seen.has(e.id)){if(data)count++;seen.add(e.id);}}
 data=v;paint();
 }catch{if(!data){text(badge,'Signal Lock недоступен · UNKNOWN. Действующего плана нет.');}if(data){data={...data,error:'CONNECTION_UNAVAILABLE'};paint();}}finally{setTimeout(poll,1500);}}
setInterval(paint,500);void poll();
})(typeof window==='undefined'?globalThis:window);

/* Local manual scenario notebook. No account, HTTP, orders or automatic fills. */
(function (root) {
  'use strict';
  const KEY = 'aura.manual.scenarios.v1', SCALE = 100000000n, LIMIT = 200;
  const MAX_BYTES = 262144, SOURCE = 'BITGET_USDT_FUTURES_BTCUSDT';
  function units(value) {
    const s = String(value);
    if (!/^(0|[1-9]\d{0,8})(\.\d{1,8})?$/.test(s)) throw Error('INVALID_NUMBER');
    const [a,b=''] = s.split('.');
    const n = BigInt(a)*SCALE + BigInt(b.padEnd(8,'0'));
    if (n <= 0n) throw Error('INVALID_NUMBER');
    return n;
  }
  const value = n => Number(n)/1e8;
  const ceilDiv = (a,b) => (a+b-1n)/b;
  function validatePlan(plan) {
    if (!plan || !['LONG','SHORT'].includes(plan.side)) throw Error('INVALID_PLAN');
    const entry=units(plan.entry), stop=units(plan.stop), target=units(plan.target), quantity=units(plan.quantity);
    if (quantity>10n*SCALE || (plan.side==='LONG' ? !(stop<entry && entry<target) : !(target<entry && entry<stop))) throw Error('INVALID_GEOMETRY');
    const canonical={side:plan.side,entry:value(entry),stop:value(stop),target:value(target),quantity:value(quantity)};
    if([entry,stop,target,quantity].some((n,i)=>units(Object.values(canonical).slice(1)[i])!==n))throw Error('DECIMAL_PRECISION');
    const loss=estimateRaw(canonical,stop), sign=plan.side==='LONG'?1n:-1n;
    const entryFill=slip(entry,sign);
    if (ceilDiv(entryFill*quantity,SCALE)>2000n*SCALE || -loss.net>50n*SCALE) throw Error('HYPOTHETICAL_RISK_LIMIT');
    return canonical;
  }
  function slip(price, direction) {
    return direction===1n?ceilDiv(price*2001n,2000n):price*1999n/2000n;
  }
  function estimateRaw(plan, exit) {
    const e=units(plan.entry),q=units(plan.quantity),sign=plan.side==='LONG'?1n:-1n;
    const entryFill=slip(e,sign), exitFill=slip(exit,-sign);
    const entryNotional=ceilDiv(entryFill*q,SCALE),exitNotional=ceilDiv(exitFill*q,SCALE);
    const fees=ceilDiv(entryNotional,1000n)+ceilDiv(exitNotional,1000n);
    const gross=sign*(exitFill-entryFill)*q/SCALE;
    return {net:gross-fees,gross,fees,entryFill,exitFill,slippage:ceilDiv(((entryFill>e?entryFill-e:e-entryFill)+(exitFill>exit?exitFill-exit:exit-exitFill))*q,SCALE)};
  }
  function estimate(plan, exit) {
    const p=validatePlan(plan), raw=estimateRaw(p,units(exit));
    return Object.fromEntries(Object.entries(raw).map(([k,n])=>[k,value(n)]));
  }
  function record(plan, id, now, timeframe, notes='') {
    if (typeof id!=='string'||!/^[-a-zA-Z0-9]{1,80}$/.test(id)||!Number.isSafeInteger(now)||now<=0||now>=4102444800||!['1m','5m','15m','1h','4h'].includes(timeframe)||typeof notes!=='string'||notes.length>280) throw Error('INVALID_RECORD');
    return {id,created_at:now,source:SOURCE,timeframe,plan:validatePlan(plan),notes,state:'PLANNED',exit:null,reviewed_at:null};
  }
  function checkRecord(r) {
    const clean=record(r.plan,r.id,r.created_at,r.timeframe,r.notes);
    if(r.source!==SOURCE||!['PLANNED','REVIEWED','CANCELLED'].includes(r.state))throw Error('INVALID_RECORD');
    if(r.state==='REVIEWED'){
      units(r.exit);
      if(!Number.isSafeInteger(r.reviewed_at)||r.reviewed_at<r.created_at||r.reviewed_at>=4102444800)throw Error('INVALID_RECORD');
      clean.exit=value(units(r.exit));if(units(clean.exit)!==units(r.exit))throw Error('DECIMAL_PRECISION');clean.reviewed_at=r.reviewed_at;
    }else if(r.exit!==null||r.reviewed_at!==null)throw Error('INVALID_RECORD');
    clean.state=r.state;return clean;
  }
  function read(storage) {
    const raw=storage.getItem(KEY);
    if(raw===null)return [];
    if(raw.length>MAX_BYTES)throw Error('JOURNAL_TOO_LARGE');
    const data=JSON.parse(raw);
    if(data.version!==1||!Array.isArray(data.entries)||data.entries.length>LIMIT)throw Error('INVALID_JOURNAL');
    const rows=data.entries.map(checkRecord);
    if(new Set(rows.map(r=>r.id)).size!==rows.length)throw Error('DUPLICATE_ID');
    return rows;
  }
  function write(storage,rows){
    const raw=JSON.stringify({version:1,entries:rows.map(checkRecord)});
    if(rows.length>LIMIT||raw.length>MAX_BYTES||new Set(rows.map(r=>r.id)).size!==rows.length)throw Error('JOURNAL_LIMIT');
    storage.setItem(KEY,raw);
  }
  function append(rows,r){
    if(rows.some(a=>a.id===r.id))return rows;
    if(rows.length>=LIMIT)throw Error('JOURNAL_LIMIT');
    return [...rows,checkRecord(r)];
  }
  function review(rows,id,exit,now){
    let found=false;
    const next=rows.map(r=>{
      if(r.id!==id)return r;
      found=true;
      if(r.state!=='PLANNED')throw Error('ALREADY_REVIEWED');
      return checkRecord({...r,state:'REVIEWED',exit,reviewed_at:now});
    });
    if(!found)throw Error('UNKNOWN_RECORD');return next;
  }
  async function mutate(storage,locks,expected,transform){
    if(!locks||typeof locks.request!=='function')throw Error('WEB_LOCKS_REQUIRED');
    return locks.request(KEY,{mode:'exclusive'},()=>{
      const current=read(storage);
      if(JSON.stringify(current)!==JSON.stringify(expected))throw Error('JOURNAL_CHANGED_RELOAD');
      const next=transform(current);write(storage,next);return next;
    });
  }
  const api={KEY,LIMIT,MAX_BYTES,units,validatePlan,estimate,record,checkRecord,read,write,append,review,mutate};
  if(typeof module!=='undefined')module.exports=api;
  root.AuraScenarioJournal=api;
  if(!root.document)return;
  const d=root.document,el=id=>d.getElementById('journal-'+id);
  if(!el('list'))return;
  let rows=[],blocked=false,selectedPlan=null,busy=false,exportAllowed=true;
  const message=t=>{el('status').textContent=t;};
  function render(){
    el('list').replaceChildren();
    for(const r of rows.slice().reverse()){
      const row=d.createElement('article'),title=d.createElement('h4'),detail=d.createElement('p');
      title.textContent=r.plan.side+' · '+r.timeframe+' · '+new Date(r.created_at*1000).toISOString();
      detail.textContent='Entry '+r.plan.entry+' · SL '+r.plan.stop+' · TP '+r.plan.target+' · BTC '+r.plan.quantity+' · '+r.state;
      row.append(title,detail);
      if(r.notes){const note=d.createElement('p');note.textContent=r.notes;row.append(note);}
      if(r.state==='REVIEWED'){
        const p=d.createElement('p'),v=estimate(r.plan,r.exit);
        p.textContent='Гипотетический выход '+r.exit+' · net '+v.net.toFixed(2)+' USDT · комиссии '+v.fees.toFixed(2)+' · проскальзывание '+v.slippage.toFixed(2)+' (включено в net)';row.append(p);
      }else if(r.state==='PLANNED'){
        const input=d.createElement('input'),button=d.createElement('button');
        input.type='number';input.min='0.00000001';input.step='0.1';input.placeholder='Цена гипотетического выхода';input.setAttribute('aria-label','Цена гипотетического выхода для '+r.id);
        button.type='button';button.textContent='Оценить исход · локально';
        button.addEventListener('click',async()=>{
          if(blocked||busy)return;busy=true;
          try{rows=await mutate(root.localStorage,root.navigator?.locks,rows,current=>review(current,r.id,input.value,Math.floor(Date.now()/1000)));render();message('Оценка сохранена локально. Это не исполненная сделка.');}catch{message('Не удалось сохранить: проверьте цену, лимиты, хранилище; после изменения в другой вкладке перезагрузите страницу.');}finally{busy=false;}
        });row.append(input,button);
      }
      el('list').append(row);
    }
    el('save').disabled=blocked||!selectedPlan;el('export').disabled=!exportAllowed;
  }
  try{rows=read(root.localStorage);message('Локальный журнал: '+rows.length+' / '+LIMIT+'. В Supabase ничего не записывается.');}catch{blocked=true;exportAllowed=false;message('Журнал недоступен или повреждён. Запись заблокирована; существующие данные не перезаписываются.');}
  root.addEventListener('aura-manual-plan',event=>{
    try{selectedPlan=validatePlan(event.detail);el('draft').textContent=selectedPlan.side+' · Entry '+selectedPlan.entry+' · SL '+selectedPlan.stop+' · TP '+selectedPlan.target+' · BTC '+selectedPlan.quantity;}catch{selectedPlan=null;el('draft').textContent='Нет допустимого ручного плана.';}render();
  });
  el('save').addEventListener('click',async()=>{
    if(blocked||busy||!selectedPlan)return;
    busy=true;
    try{
      const now=Math.floor(Date.now()/1000),notes=el('notes').value,tf=d.getElementById('drawing-timeframe').textContent;
      const fingerprint=JSON.stringify([selectedPlan,tf,notes]);
      if(rows.some(r=>r.state==='PLANNED'&&JSON.stringify([r.plan,r.timeframe,r.notes])===fingerprint)){message('Этот план уже есть в локальном журнале.');return;}
      const r=record(selectedPlan,root.crypto.randomUUID(),now,tf,notes);
      rows=await mutate(root.localStorage,root.navigator?.locks,rows,current=>append(current,r));render();message('План сохранён только в этом браузере. Никаких ордеров.');
    }catch{message('Запись не выполнена: лимит 200, риск до 50 USDT, номинал до 2000 USDT; проверьте хранилище.');}finally{busy=false;}
  });
  el('export').addEventListener('click',()=>{
    if(!exportAllowed)return;
    const blob=new Blob([JSON.stringify({version:1,scope:'MANUAL_HYPOTHETICAL_ONLY',entries:rows},null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=d.createElement('a');
    a.href=url;a.download='aura-manual-scenarios.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  root.addEventListener('storage',event=>{if(event.key===KEY){blocked=true;exportAllowed=false;selectedPlan=null;message('Журнал изменён в другой вкладке. Перезагрузите страницу перед записью.');render();}});
  if(!root.navigator?.locks){blocked=true;message('Запись требует Web Locks в HTTPS-браузере. Чтение и экспорт доступны после проверки данных.');}
  render();
})(typeof window==='undefined'?globalThis:window);

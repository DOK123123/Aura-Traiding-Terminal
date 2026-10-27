/* Original SVG drawing layer over the existing Lightweight Charts 5 chart.
 * User annotations only; never feeds indicators, signals, PAPER or exchange APIs.
 */
(function(root){
  'use strict';
  const KEY='aura.manual.drawings.v1',LIMIT=40,MAX_BYTES=196608;
  const STEPS={'1m':60,'5m':300,'15m':900,'1h':3600,'4h':14400};
  const TYPES=['horizontal','trend','zone','fib','plan'];
  const finite=n=>typeof n==='number'&&Number.isFinite(n);
  const point=p=>p&&Number.isSafeInteger(p.time)&&p.time>0&&p.time<4102444800&&finite(p.price)&&p.price>0&&p.price<1e8;
  function cleanShape(s){
    if(!s||typeof s.id!=='string'||!/^[-a-zA-Z0-9]{1,80}$/.test(s.id)||!TYPES.includes(s.type)||!Array.isArray(s.points)||s.points.length!==(s.type==='horizontal'?1:s.type==='plan'?3:2)||!s.points.every(point))throw Error('INVALID_DRAWING');
    if(s.type==='plan'&&(!['LONG','SHORT'].includes(s.side)||!finite(s.quantity??0.001)||(s.quantity??0.001)<=0||(s.quantity??0.001)>10))throw Error('INVALID_PLAN');
    return {id:s.id,type:s.type,points:s.points.map(p=>({time:p.time,price:p.price})),...(s.type==='plan'?{side:s.side,quantity:s.quantity??0.001}:{})};
  }
  function decode(raw){
    if(raw===null)return {version:1,frames:{}};
    if(typeof raw!=='string'||raw.length>MAX_BYTES)throw Error('DRAWING_LIMIT');
    const data=JSON.parse(raw);
    if(data.version!==1||!data.frames||typeof data.frames!=='object'||Array.isArray(data.frames)||Object.keys(data.frames).some(f=>!Object.hasOwn(STEPS,f)))throw Error('INVALID_DRAWINGS');
    const frames={};
    for(const [tf,shapes]of Object.entries(data.frames)){
      if(!Array.isArray(shapes)||shapes.length>LIMIT)throw Error('DRAWING_LIMIT');
      frames[tf]=shapes.map(cleanShape);
      if(new Set(frames[tf].map(s=>s.id)).size!==shapes.length)throw Error('DUPLICATE_DRAWING');
    }
    return {version:1,frames};
  }
  function fibLevels(a,b){
    if(!point(a)||!point(b)||a.price===b.price)throw Error('INVALID_FIB');
    return [0,.236,.382,.5,.618,.786,1].map(r=>({ratio:r,price:b.price+(a.price-b.price)*r}));
  }
  function movePoint(shape,index,p){
    const s=cleanShape(shape);
    if(!Number.isInteger(index)||index<0||index>=s.points.length||!point(p))throw Error('INVALID_HANDLE');
    s.points[index]={time:p.time,price:p.price};return s;
  }
  const api={KEY,LIMIT,decode,cleanShape,fibLevels,movePoint};
  if(typeof module!=='undefined')module.exports=api;
  root.AuraChartTools=api;
  if(!root.document)return;
  let attached=false;
  api.attach=function({chart,series,getContext}){
    if(attached)return;attached=true;
    const d=root.document,el=id=>d.getElementById('drawing-'+id),host=d.getElementById('chart');
    if(!host||!el('tool'))return;
    const NS='http://www.w3.org/2000/svg',svg=d.createElementNS(NS,'svg');
    svg.setAttribute('class','manual-overlay');svg.setAttribute('aria-label','Ручные аннотации графика');host.append(svg);
    const rangeHelper=chart.addSeries(root.LightweightCharts.LineSeries,{lineVisible:false,pointMarkersVisible:false,lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false});
    let db={version:1,frames:{}},blocked=false,tf=null,selected=null,first=null,drag=null,raf=null,analyst=null,rangeSignature=null;
    const msg=t=>{el('status').textContent=t;};
    try{db=decode(root.localStorage.getItem(KEY));}catch{blocked=true;msg('Аннотации недоступны или повреждены. Сохранение заблокировано; данные не перезаписываются.');}
    const shapes=()=>db.frames[tf]||[];
    const context=()=>getContext();
    function sync(){
      const c=context();
      if(c.symbol!=='BTCUSDT'||!Object.hasOwn(STEPS,c.timeframe))return false;
      if(tf!==c.timeframe){tf=c.timeframe;selected=null;first=null;drag=null;el('timeframe').textContent=tf;el('tool').value='select';svg.style.pointerEvents='none';root.dispatchEvent(new CustomEvent('aura-manual-plan',{detail:null}));el('risk').textContent='Новый таймфрейм: выберите или создайте ручной план.';const plan=(db.frames[tf]||[]).findLast(s=>s.type==='plan');if(plan){selected=plan.id;emitPlan(plan);}}
      return c.candles.length>0;
    }
    function persist(){
      if(blocked){msg('Сохранение заблокировано.');return false;}
      try{const raw=JSON.stringify(db);decode(raw);root.localStorage.setItem(KEY,raw);return true;}
      catch{blocked=true;msg('Не удалось сохранить аннотации. Память браузера может быть заполнена; экспортируйте журнал.');return false;}
    }
    function xy(p){
      const c=context(),firstBar=c.candles[0];
      if(!firstBar)return null;
      const x=chart.timeScale().logicalToCoordinate((p.time-firstBar.time)/STEPS[tf]),y=series.priceToCoordinate(p.price);
      return finite(x)&&finite(y)?{x,y}:null;
    }
    function fromEvent(event){
      const rect=host.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;
      // Do not capture price/time axes or extrapolate price from invalid scales.
      const width=chart.timeScale().width(),height=host.clientHeight-chart.timeScale().height();
      if(x<0||x>width||y<0||y>Math.min(height,rect.height-26))return null;
      const c=context(),logical=chart.timeScale().coordinateToLogical(x),price=series.coordinateToPrice(y);
      if(!finite(logical)||!c.candles.length||!finite(price))return null;
      const p={time:c.candles[0].time+Math.round(logical)*STEPS[tf],price:Math.round(price*1e8)/1e8};
      return point(p)?p:null;
    }
    function node(tag,attrs={},text){
      const n=d.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,String(v));
      if(text!==undefined)n.textContent=text;return n;
    }
    function render(){
      raf=null;svg.replaceChildren();if(!sync()){if(rangeSignature!=='[]'){rangeHelper.setData([]);rangeSignature='[]';}return;}
      const plans=shapes().filter(s=>s.type==='plan'),tail=context().candles.slice(-2);
      const rangeData=plans.length&&tail.length===2?[{time:tail[0].time,value:Math.min(...plans.flatMap(s=>s.points.map(p=>p.price)))},{time:tail[1].time,value:Math.max(...plans.flatMap(s=>s.points.map(p=>p.price)))}]:[];
      const signature=JSON.stringify(rangeData);if(signature!==rangeSignature){rangeSignature=signature;rangeHelper.setData(rangeData);}
      svg.setAttribute('viewBox',`0 0 ${host.clientWidth} ${host.clientHeight}`);
      const width=chart.timeScale().width();
      for(const s of shapes()){
        const pts=s.points.map(xy);if(pts.some(p=>!p))continue;
        const color=s.type==='plan'?'#f4c779':s.type==='zone'?'#9c8bf7':'#6cddc3';
        const group=node('g',{'data-drawing-id':s.id});
        const line=(x1,y1,x2,y2,label,stroke=color)=>{
          const n=node('line',{x1,y1,x2,y2,stroke,'stroke-width':s.id===selected?2.5:1.5,'data-id':s.id});
          n.style.pointerEvents='stroke';group.append(n);
          if(label)group.append(node('text',{x:Math.max(4,Math.min(x1+5,width-200)),y:y1-5,fill:stroke,'font-size':11},label));
        };
        if(s.type==='trend')line(pts[0].x,pts[0].y,pts[1].x,pts[1].y,'Линия · вручную');
        if(s.type==='zone'){
          const r=node('rect',{x:Math.min(pts[0].x,pts[1].x),y:Math.min(pts[0].y,pts[1].y),width:Math.abs(pts[1].x-pts[0].x),height:Math.abs(pts[1].y-pts[0].y),fill:'#9c8bf722',stroke:color,'data-id':s.id});r.style.pointerEvents='all';group.append(r);
        }
        if(s.type==='horizontal')line(0,pts[0].y,width,pts[0].y,s.points[0].price.toFixed(2)+' · уровень');
        if(s.type==='fib'&&s.points[0].price!==s.points[1].price){
          for(const f of fibLevels(...s.points)){const y=series.priceToCoordinate(f.price);if(finite(y))line(Math.min(pts[0].x,pts[1].x),y,Math.max(pts[0].x,pts[1].x),y,(f.ratio*100).toFixed(1)+'% · '+f.price.toFixed(2));}
        }
        if(s.type==='plan')for(let i=0;i<3;i++)line(0,pts[i].y,width,pts[i].y,['Entry','SL','TP'][i]+' · '+s.points[i].price.toFixed(2),['#f4c779','#fa788b','#42d6b0'][i]);
        if(s.id===selected)pts.forEach((p,i)=>{const handle=node('circle',{cx:p.x,cy:p.y,r:8,fill:color,stroke:'#111720','data-id':s.id,'data-handle':i});handle.style.pointerEvents='all';group.append(handle);});
        svg.append(group);
      }
      if(first){const p=xy(first);if(p)svg.append(node('circle',{cx:p.x,cy:p.y,r:5,fill:'#f4c779'}));}
      el('delete').disabled=!selected||blocked;
    }
    function schedule(){if(raf===null)raf=root.requestAnimationFrame(render);}
    function emitPlan(s){
      if(!s||s.type!=='plan')return;
      el('side').value=s.side;el('quantity').value=String(s.quantity);['entry','stop','target'].forEach((k,i)=>{el(k).value=String(s.points[i].price);});
      try{
        const plan=root.AuraScenarioJournal.validatePlan({side:s.side,entry:s.points[0].price,stop:s.points[1].price,target:s.points[2].price,quantity:el('quantity').value});
        const loss=root.AuraScenarioJournal.estimate(plan,plan.stop),gain=root.AuraScenarioJournal.estimate(plan,plan.target);
        el('risk').textContent='Гипотетический риск '+(-loss.net).toFixed(2)+' USDT · R/R net '+(gain.net/-loss.net).toFixed(2)+' · расходы при SL '+loss.fees.toFixed(2)+' fee + '+loss.slippage.toFixed(2)+' slip. Funding не включён.';
        root.dispatchEvent(new CustomEvent('aura-manual-plan',{detail:plan}));
      }catch{el('risk').textContent='Неверная геометрия или превышены учебные лимиты: риск 50 USDT / номинал 2000 USDT. Это не приказ на биржу.';root.dispatchEvent(new CustomEvent('aura-manual-plan',{detail:null}));}
    }
    function add(type,points,side,quantity){
      if(blocked||shapes().length>=LIMIT){msg('Сохранение недоступно или достигнут лимит 40 объектов на таймфрейм.');return;}
      const shape=cleanShape({id:root.crypto.randomUUID(),type,points,side,quantity});
      if(type==='fib'&&points[0].price===points[1].price){msg('Для Фибоначчи нужны разные цены.');return;}
      db.frames[tf]=[...shapes(),shape];selected=shape.id;const saved=persist();emitPlan(shape);schedule();return saved;
    }
    el('tool').addEventListener('change',()=>{
      first=null;svg.style.pointerEvents=el('tool').value==='select'?'none':'all';
      svg.style.touchAction=el('tool').value==='select'?'auto':'none';
      msg('Ручная разметка: '+(el('tool').value==='horizontal'?'одно касание':el('tool').value==='select'?'выберите объект, затем двигайте круглые маркеры':'два касания графика. Escape — отмена')+'. Не торговый сигнал.');schedule();
    });
    svg.addEventListener('pointerdown',event=>{
      if(!sync()||blocked)return;
      const id=event.target.getAttribute('data-id'),index=event.target.getAttribute('data-handle');
      if(id&&el('tool').value==='select'){
        selected=id;emitPlan(shapes().find(s=>s.id===id));
        if(index!==null){drag={id,index:Number(index),before:JSON.stringify(db),pointer:event.pointerId};svg.setPointerCapture(event.pointerId);svg.style.touchAction='none';}
        event.preventDefault();schedule();return;
      }
      const tool=el('tool').value,p=fromEvent(event);if(tool==='select'||!p)return;
      event.preventDefault();
      if(tool==='horizontal')add(tool,[p]);else if(!first){first=p;}else{add(tool,[first,p]);first=null;}
      schedule();
    });
    svg.addEventListener('pointermove',event=>{
      if(!drag||event.pointerId!==drag.pointer)return;
      const p=fromEvent(event);if(!p)return;
      db.frames[tf]=shapes().map(s=>s.id===drag.id?movePoint(s,drag.index,p):s);schedule();
    });
    function finish(event,cancel=false){
      if(!drag)return;
      if(event&&event.pointerId!==drag.pointer)return;
      const id=drag.id;
      if(cancel)db=decode(drag.before);else persist();
      if(svg.hasPointerCapture(drag.pointer))svg.releasePointerCapture(drag.pointer);
      drag=null;svg.style.touchAction=el('tool').value==='select'?'auto':'none';emitPlan(shapes().find(s=>s.id===id));schedule();
    }
    svg.addEventListener('pointerup',event=>finish(event));svg.addEventListener('pointercancel',event=>finish(event,true));
    d.addEventListener('keydown',event=>{if(event.key==='Escape'){finish(null,true);first=null;el('tool').value='select';svg.style.pointerEvents='none';schedule();}});
    el('delete').addEventListener('click',()=>{if(blocked)return;db.frames[tf]=shapes().filter(s=>s.id!==selected);selected=null;root.dispatchEvent(new CustomEvent('aura-manual-plan',{detail:null}));persist();schedule();});
    el('apply').addEventListener('click',()=>{
      if(!sync())return;
      try{
        const p=root.AuraScenarioJournal.validatePlan({side:el('side').value,entry:el('entry').value,stop:el('stop').value,target:el('target').value,quantity:el('quantity').value});
        const time=context().candles.at(-1).time,points=[p.entry,p.stop,p.target].map(price=>({price,time}));
        const shape=shapes().find(s=>s.id===selected&&s.type==='plan');
        let saved=false;
        if(shape&&!blocked){db.frames[tf]=shapes().map(s=>s.id===selected?{...s,side:p.side,quantity:p.quantity,points}:s);saved=persist();emitPlan(shapes().find(s=>s.id===selected));schedule();}
        else saved=add('plan',points,p.side,p.quantity);
        if(saved)msg('Ручной план нанесён и сохранён локально; это не заявка и не исполненная сделка.');
      }catch{msg('Проверьте Entry/SL/TP, BTC и лимиты учебного риска.');root.dispatchEvent(new CustomEvent('aura-manual-plan',{detail:null}));}
    });
    root.addEventListener('aura-analyst-snapshot',event=>{analyst=event.detail;el('copy').disabled=!analyst?.scenario||!analyst?.fresh;});
    el('copy').addEventListener('click',()=>{
      if(!analyst?.fresh||!analyst.scenario||analyst.valid_until<=Date.now()/1000){analyst=null;el('copy').disabled=true;msg('Анализ устарел.');return;}
      const p=analyst.scenario;el('side').value=analyst.state;el('entry').value=p.reference_entry;el('stop').value=p.stop_loss;el('target').value=p.take_profit;
      msg('Скопированы только ориентиры аналитики. Проверьте количество и нажмите «Нанести план».');
    });
    // Existing market stream supplies chart snapshots; never emit trading events.
    d.addEventListener('market-data-changed',schedule);
    chart.timeScale().subscribeVisibleLogicalRangeChange(schedule);
    chart.subscribeCrosshairMove(schedule);
    const observer=new ResizeObserver(schedule);observer.observe(host);
    root.addEventListener('storage',event=>{if(event.key===KEY){blocked=true;msg('Разметка изменена в другой вкладке. Перезагрузите страницу перед сохранением.');}});
    root.addEventListener('pagehide',()=>{finish(null,true);first=null;});
    schedule();
    api.refresh=schedule;
  };
})(typeof window==='undefined'?globalThis:window);

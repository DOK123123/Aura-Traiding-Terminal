/* Public-data analysis only. No paper mutation, replay action or exchange client. */
(() => {
  'use strict';
  const labels={BROWSER_TIMEOUT:'Браузер не дождался ответа сервера',LOADING:'Загрузка…',READY:'Свежие закрытые свечи',STALE_DATA:'НЕАКТУАЛЬНО — показан последний успешный анализ',UPSTREAM_TIMEOUT:'Источник не ответил вовремя',ANALYSIS_TIMEOUT:'Анализ не завершён вовремя',DATA_UNAVAILABLE:'Данные недоступны',ERROR:'Ошибка обновления',FRESH:'Свежие закрытые свечи',STALE:'Данные устарели',UNAVAILABLE:'Источник недоступен',INSUFFICIENT_HISTORY:'Недостаточно истории для прогрева',TIMEOUT:'Превышено время ожидания',NETWORK_ERROR:'Ошибка сети',RATE_LIMIT:'Ограничение частоты запросов',REGION_RESTRICTED:'Источник недоступен из региона сервера',UPSTREAM_HTTP_ERROR:'Ошибка публичного источника',INVALID_DATA:'Некорректные данные',INVALID_OHLCV:'Некорректные OHLCV',INVALID_TIMESTAMPS:'Некорректные временные метки',INVALID_CLOSE_TIME:'Некорректное время закрытия',DUPLICATE_OR_UNORDERED:'Дубликаты или нарушенный порядок свечей',DATA_LIMIT:'Превышен защитный лимит данных',NO_EDGE_FOUND:'Подтверждённого преимущества не найдено',TREND_UP:'Восходящий тренд',TREND_DOWN:'Нисходящий тренд',RANGE:'Боковой рынок',UNKNOWN:'Не определено',EXPANSION:'Расширение',COMPRESSION:'Сжатие',NORMAL:'Обычная',HH:'Более высокий максимум',HL:'Более высокий минимум',LH:'Более низкий максимум',LL:'Более низкий минимум',EQUAL:'Равные экстремумы',LONG:'Вверх',SHORT:'Вниз',UP:'Вверх',DOWN:'Вниз',AMBIGUOUS:'Двустороннее событие; направление неизвестно',BOS:'Пробой подтверждённой структуры',CHoCH:'Изменение характера структуры',HIGH:'Максимум',LOW:'Минимум',CONFIRMED_PIVOT:'Подтверждённые экстремумы',ROLLING50_FALLBACK:'Экстремум последних 50 свечей (резерв)',breakout:'Пробой',failed_breakout:'Неудавшийся пробой',retest:'Повторный тест пробитого уровня',structure_event:'Структурное событие',liquidity_sweep:'Вынос уровня с возвратом',swing:'Подтверждённый экстремум'};
  const label=value=>labels[value]||'Не определено';
  const number=value=>value===null||value===undefined||value===''?'—':Number.isFinite(Number(value))?Number(value).toLocaleString('ru-RU',{maximumFractionDigits:3}):'—';
  const date=value=>Number.isFinite(value)?new Date(value*1000).toLocaleString('ru-RU',{timeZone:'UTC',hour12:false})+' UTC':'—';
  function model(data,elapsed=0){
    const seconds=elapsed/1000,step={'15m':900,'1h':3600,'4h':14400}[data?.timeframe];
    const expired=elapsed>90000||Number.isFinite(data?.freshness?.age_seconds)&&data.freshness.age_seconds+seconds>=step||Number.isFinite(data?.freshness?.base_age_seconds)&&data.freshness.base_age_seconds+seconds>=900||Number.isFinite(data?.freshness?.delivery_age_seconds)&&data.freshness.delivery_age_seconds+seconds>90;
    const usable=data?.status==='OK'&&data?.freshness?.status==='FRESH'&&data.state&&!expired;
    const retained=data?.last_successful_analysis;
    const display=usable?data:retained||(expired&&data?.state?data:null);
    const phase=usable?'READY':display?'STALE_DATA':['UPSTREAM_TIMEOUT','ANALYSIS_TIMEOUT'].includes(data?.status)?data.status:['UNAVAILABLE','INSUFFICIENT_HISTORY'].includes(data?.status)||!data?'DATA_UNAVAILABLE':data?.status==='STALE'?'STALE_DATA':'ERROR';
    const status=expired?'STALE':data?.status==='OK'?data.freshness?.status:data?.status||'UNAVAILABLE';
    return {usable,phase,status:(display&&!usable?'НЕАКТУАЛЬНО — последний успешный анализ. ':'')+label(data?.reason==='BROWSER_TIMEOUT'?'BROWSER_TIMEOUT':status),state:display?.state||null,
      regime:display?label(display.regime):'Не определено',levels:display?.levels||null,
      events:display?.structure_events||[],mtf:display?.mtf||null,
      decision:'WAIT — только чтение. '+(usable?'Подтверждённого преимущества нет; нужна независимая forward-проверка.':'Нет свежего доступного анализа. Сделки не предлагаются.'),
      analogs:'Статистика аналогов недоступна: совместимый проверенный пакет версии 3.0 не установлен.',
      history:display?.history||data?.history,definitions:display?.definitions||data?.definitions,source:display?.source||data?.source||'Не доступен',closed:date(display?.last_closed_at??data?.last_closed_at),fetched:date(display?.fetched_at??data?.fetched_at)};
  }
  function createReader(fetcher,onValue,onPending){
    let busy=false,controller=null,generation=0,closed=false;
    const successful=new Map();
    function deliver(data,status,tf){
      if(!data||typeof data!=='object'||Array.isArray(data)||data.status==='OK'&&data.timeframe!==tf)data={status:'INVALID_DATA',timeframe:tf};
      if(data?.status==='OK'&&data?.freshness?.status==='FRESH'&&data.timeframe===tf)successful.set(tf,data);
      else if(status!==401&&status!==403&&!data.last_successful_analysis&&successful.has(tf))data={...data,last_successful_analysis:successful.get(tf)};
      if(status===401||status===403)successful.clear();
      onValue(data,status);
    }
    return {
      get busy(){return busy;},
      async read(tf){
        if(busy||closed)return false;
        busy=true;controller=new AbortController();const aborter=controller,current=++generation;onPending(true);
        const timer=setTimeout(()=>aborter.abort(),24000);
        try{
          const response=await fetcher('/api/intelligence/market-context?timeframe='+encodeURIComponent(tf),{method:'GET',credentials:'same-origin',cache:'no-store',signal:aborter.signal});
          const data=await response.json();
          if(!closed&&generation===current)deliver(data,response.status,tf);
        }catch{
          if(!closed&&generation===current)deliver({status:aborter.signal.aborted?'ERROR':'UNAVAILABLE',reason:aborter.signal.aborted?'BROWSER_TIMEOUT':'NETWORK_ERROR',timeframe:tf},0,tf);
        }finally{
          clearTimeout(timer);if(generation===current){busy=false;controller=null;onPending(false);}
        }
        return true;
      },
      invalidate(){generation++;controller?.abort();controller=null;busy=false;onPending(false);},
      close(){this.invalidate();closed=true;}
    };
  }
  if(typeof module!=='undefined')module.exports={model,createReader,labels,number,date};
  if(typeof document==='undefined')return;
  const $=id=>document.getElementById(id);if(!$('mc-panel'))return;
  let active=false,data=null,received=0;
  const text=(id,value)=>{$(id).textContent=String(value);};
  function list(id,items){const parent=$(id);parent.replaceChildren();for(const s of items){const li=document.createElement('li');li.textContent=s;parent.append(li);}}
  function render(){
    const m=model(data,received?Date.now()-received:0),s=m.state;
    $('mc-panel').setAttribute('data-state',reader.busy?'LOADING':m.phase);text('mc-status',m.status);text('mc-decision',m.decision);text('mc-regime',m.regime);
    text('mc-source',m.source+' · последняя закрытая свеча: '+m.closed+' · последнее успешное обновление: '+m.fetched);
    text('mc-structure',s?label(s.high_leg)+' / '+label(s.low_leg)+' · ADX '+number(s.trend_strength)+' · RSI '+number(s.rsi):'Структура и индикаторы не доступны');
    text('mc-levels',m.levels?'Поддержка '+number(m.levels.support)+' USDT ('+label(m.levels.support_source)+') · сопротивление '+number(m.levels.resistance)+' USDT ('+label(m.levels.resistance_source)+')':'Уровни не доступны');
    text('mc-smc',s?'Экспериментальный FVG: '+(s.fvg?label(s.fvg.side)+' · '+number(s.fvg.lower)+'–'+number(s.fvg.upper)+' · подтверждено '+date(s.fvg.confirmation_time):'не обнаружен')+' · блок тела перед пробоем: '+(s.order_block?label(s.order_block.side)+' · '+number(s.order_block.lower)+'–'+number(s.order_block.upper)+' · подтверждено '+date(s.order_block.confirmation_time):'не обнаружен'):'Экспериментальные структуры не доступны');
    text('mc-volatility',s?'Волатильность: '+label(s.volatility)+' · ATR '+number(s.atr)+' USDT · относительный объём '+number(s.relative_volume)+(s.relative_volume===null?' — нет базы объёма':s.volume_confirmed?' · объём подтверждён':' · без подтверждения объёмом')+' · глубина отката '+number(s.pullback_depth_atr)+' ATR':'Волатильность и объём не доступны');
    list('mc-mtf',m.mtf?['h1','h4'].map(k=>k==='h1'?'1h: '+(m.mtf[k]?label(m.mtf[k].direction===1?'UP':m.mtf[k].direction===-1?'DOWN':'UNKNOWN')+' · '+date(m.mtf[k].closed_at):'Недостаточно непрерывной истории'):'4h: '+(m.mtf[k]?label(m.mtf[k].direction===1?'UP':m.mtf[k].direction===-1?'DOWN':'UNKNOWN')+' · '+date(m.mtf[k].closed_at):'Недостаточно непрерывной истории')).concat(m.mtf.known_mask===3?[m.mtf.alignment?'Направления совпадают':'Направления не совпадают']:['Полное согласование не определено']):['Межтаймфреймовое согласование не доступно']);
    list('mc-events',m.events.length?m.events.slice().reverse().map(e=>label(e.type)+' · '+label(e.value||e.kind)+' · подтверждено '+date(e.confirmed_at||e.confirmation_time)+(e.pivot_time!==undefined?' · экстремум '+date(e.pivot_time)+' · '+number(e.price)+' USDT':'')):['Нет обнаруженных событий в последних 32 доступных свечах / анализ недоступен']);
    text('mc-analogs',m.analogs);text('mc-research','Исследование 3.0: 42 конфигурации, 0 прошедших кандидатов. Это не оценка доходности текущего сигнала. Пакет replay 1.0 несовместим и не применяется.');
    text('mc-history',m.history?'Окно: '+m.history.base_count+' свечей 15m; непрерывный хвост '+m.history.continuous_base_count+'; пропущено '+m.history.missing_candles+'; прогрев 250 свечей каждого таймфрейма.'+(m.history.complete===false?' Запрошенное окно получено не полностью.':'')+' SHA256 '+m.history.source_sha256:'История ещё не доступна');
    list('mc-definitions',m.definitions?Object.values(m.definitions):['Определения будут загружены вместе с анализом']);
  }
  const reader=createReader(fetch,(value,status)=>{data=value;received=Date.now();render();if(status===401||status===403)text('mc-status','Требуется вход владельца (aura); настройка доступа как у существующего Paper/Replay.');},pending=>{$('mc-panel').setAttribute('data-state',pending?'LOADING':model(data,received?Date.now()-received:0).phase);$('mc-refresh').disabled=pending;text('mc-loading',pending?'Анализ обновляется…':'');$('mc-panel').setAttribute('aria-busy',String(pending));});
  function activate(which,focus=false){
    active=which==='market';$('mc-panel').hidden=!active;$('ai-replay-panel').hidden=active;
    for(const [id,selected]of[['mc-tab-market',active],['mc-tab-replay',!active]]){$(id).setAttribute('aria-selected',String(selected));$(id).tabIndex=selected?0:-1;if(selected&&focus)$(id).focus();}
    if(active){render();reader.read($('mc-timeframe').value);}else reader.invalidate();
  }
  $('mc-tab-market').addEventListener('click',()=>activate('market'));
  $('mc-tab-replay').addEventListener('click',()=>activate('replay'));
  for(const id of ['mc-tab-market','mc-tab-replay'])$(id).addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();activate(event.key==='Home'?'replay':event.key==='End'?'market':active?'replay':'market',true);}});
  $('mc-refresh').addEventListener('click',()=>reader.read($('mc-timeframe').value));
  $('mc-timeframe').addEventListener('change',()=>{reader.invalidate();data=null;received=0;render();reader.read($('mc-timeframe').value);});
  const timer=setInterval(()=>{if(active&&!document.hidden){render();reader.read($('mc-timeframe').value);}},60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&active){render();reader.read($('mc-timeframe').value);}});
  const freshnessTimer=setInterval(()=>{if(active&&!document.hidden)render();},5000);
  window.addEventListener('pagehide',()=>{reader.close();clearInterval(timer);clearInterval(freshnessTimer);});
  // Preserve replay as default. A deep link opens read-only analysis, never execution.
  if(location.hash==='#market-analysis')activate('market');
})();

/* Public closed-candle manual analysis. No account or trading controls. */
(function(root){'use strict';
 const STEPS={'5m':300,'15m':900,'1h':3600,'4h':14400},SOURCE='Bitget · USDT-M Futures / api.bitget.com';
 const labels={TREND_NOT_CONFIRMED:'Направление EMA не подтверждено одновременно на 5m, 15m и 1h.',CONFLICTING_4H_CONTEXT:'Контекст 4h противоречит сценарию.',NO_ORDERED_SWING:'Не найден последовательный прошлый импульс для Фибоначчи.',RSI_NOT_CONFIRMED:'RSI не подтверждает умеренный импульс: LONG 52–68, SHORT 32–48.',NO_ENTRY_CONFLUENCE:'Нет близкой зоны совпадения EMA20 и Фибоначчи 38,2–61,8%.',CLOSED_CANDLE_NOT_CONFIRMED:'Последняя закрытая свеча не подтвердила возобновление движения.',INSUFFICIENT_RR_AFTER_COSTS:'Потенциальная прибыль после расходов недостаточна: R/R ниже 1,5.',INVALID_SCENARIO_GEOMETRY:'Недостаточно пространства для корректных SL и TP.',TREND_5M_15M_1H:'Направление EMA20/50 согласовано на 5m, 15m и 1h.',CLOSED_RSI_MOMENTUM:'RSI 5m подтверждает умеренный импульс; старшие RSI показаны как контекст.',EMA_FIBONACCI_CONFLUENCE:'Есть совпадение EMA20 и прошлых уровней Фибоначчи.',CLOSED_CANDLE_CONFIRMATION:'Подтверждение получено закрытой свечой 5m.',RR_AFTER_COSTS:'R/R после моделируемых расходов не ниже 1,5.',RATE_LIMIT:'Bitget ограничил частоту запросов; повтор позже.',RATE_LIMIT_COOLDOWN:'Пауза после ограничения Bitget.',ANALYST_UNAVAILABLE:'Аналитический модуль недоступен; торговые настройки не изменены.',ANALYSIS_BUSY:'Предыдущий анализ ещё выполняется.',EXCHANGE_CLOSE_NOT_CONFIRMED:'Граница закрытия свечи по времени Bitget ещё не подтверждена. Подождите обновления.',SNAPSHOT_EXPIRED:'Во время анализа закрылась новая свеча. Обновите данные.',SCENARIO_EXPIRED:'Сценарий устарел. Нужен новый анализ.',UPSTREAM_TIMEOUT:'Bitget не ответил вовремя.',NETWORK_ERROR:'Нет подтверждённого соединения с Bitget.',HTTP_ERROR:'Публичный источник Bitget вернул ошибку.',REGION_OR_ACCESS_RESTRICTED:'Bitget недоступен из региона сервера.',UPSTREAM_CLOCK_OR_STALE_RESPONSE:'Ответ или время Bitget не прошли проверку свежести.',INVALID_CLOSED_HISTORY:'История неполная или не прошла проверку.',MISSING_CANDLES:'В истории отсутствуют свечи.',INCOMPLETE_HISTORY:'Недостаточно закрытых свечей.',SOURCE_MISMATCH:'Источник не подтверждает BTCUSDT USDT-M Futures.',NO_CONFIRMED_SCENARIO:'Подтверждённого ручного сценария нет.'};
 const positive=n=>typeof n==='number'&&Number.isFinite(n)&&n>0;
 const num=n=>Number.isFinite(n)?new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(n):'—';
 const utc=n=>Number.isFinite(n)?new Date(n*1000).toISOString().replace('T',' ').replace('.000Z',' UTC'):'—';
 function view(b,now=Date.now()/1000){
  const empty={state:'WAIT',scenario:null,frames:{},fibonacci:null,reasons:['Нет свежего подтверждённого анализа. Обновите данные.'],fresh:false};
  if(!b||b.version!=='AURA_MANUAL_ANALYST_1'||b.source!==SOURCE||b.symbol!=='BTCUSDT'||b.market!=='USDT-M Futures'||b.read_only!==true||b.manual_only!==true||b.exchange_execution!==false||b.profitability_verified!==false||!['LONG','SHORT','WAIT'].includes(b.state)||!Number.isFinite(b.generated_at)||now-b.generated_at>75||now-b.generated_at< -3||!Array.isArray(b.reasons))return empty;
  const reasons=b.reasons.slice(0,12).map(r=>labels[r]||'Недостаточно подтверждений или источник недоступен.');
  const valid=Object.entries(STEPS).every(([tf,step])=>{const f=b.frames?.[tf];return f&&['LONG','SHORT','NEUTRAL'].includes(f.trend)&&[f.ema20,f.ema50,f.close].every(positive)&&Number.isFinite(f.atr)&&f.atr>=0&&Number.isFinite(f.rsi)&&f.rsi>=0&&f.rsi<=100&&Number.isInteger(f.bars)&&f.bars>=100&&f.bars<=300&&f.last_closed_at===Math.floor(now/step)*step;});
  if(!valid)return {...empty,reasons};
  if(b.cost_model?.fee_per_side!==.001||b.cost_model?.adverse_slippage_per_side!==.0005||b.cost_model?.funding!=='NOT_INCLUDED')return empty;
  if(!Number.isFinite(b.valid_until)||b.valid_until<=now||b.valid_until>b.generated_at+60)return {...empty,reasons:[labels.SCENARIO_EXPIRED]};
  let scenario=null,state='WAIT';const p=b.scenario;
  if(b.state!=='WAIT'&&['TREND_5M_15M_1H','CLOSED_RSI_MOMENTUM','EMA_FIBONACCI_CONFLUENCE','CLOSED_CANDLE_CONFIRMATION','RR_AFTER_COSTS'].every(r=>b.reasons.includes(r))&&p&&[p.entry_zone?.low,p.entry_zone?.high,p.stop_loss,p.take_profit,p.reference_entry,p.net_rr,p.gross_rr].every(positive)&&p.entry_zone.low<=p.entry_zone.high&&p.net_rr>=1.5&&p.net_rr<=p.gross_rr&&p.execution==='MANUAL_REVIEW_ONLY'){
   const long=b.state==='LONG';
   if(long?p.stop_loss<p.entry_zone.low&&p.take_profit>p.entry_zone.high&&p.reference_entry===p.entry_zone.high:p.stop_loss>p.entry_zone.high&&p.take_profit<p.entry_zone.low&&p.reference_entry===p.entry_zone.low){scenario=p;state=b.state;}
  }
  const fib=b.fibonacci;
  const fibonacci=fib&&['up','down'].includes(fib.direction)&&fib.timeframe==='15m'&&fib.lookback_bars===60&&[fib.low_at,fib.high_at].every(t=>Number.isInteger(t)&&t>=b.frames['15m'].last_closed_at-61*900&&t<=b.frames['15m'].last_closed_at-1800)&&positive(fib.low)&&positive(fib.high)&&fib.low<fib.high&&['0.236','0.382','0.500','0.618','0.786'].every(k=>positive(fib.levels?.[k])&&fib.levels[k]>=fib.low&&fib.levels[k]<=fib.high)?fib:null;
  if(scenario&&(!fibonacci||fibonacci.direction!==(state==='LONG'?'up':'down'))){scenario=null;state='WAIT';}
  return {state,scenario,frames:b.frames,fibonacci,reasons:state==='WAIT'&&b.state!=='WAIT'?['План не прошёл проверку геометрии; WAIT.']:reasons,fresh:true,generated:b.generated_at,closed:b.asof_closed_at,valid_until:b.valid_until};
 }
 if(typeof module!=='undefined')module.exports={view,labels};
 if(!root.document)return;
 const d=root.document,el=id=>d.getElementById('analyst-'+id);if(!el('refresh'))return;
 let data=null,busy=false,controller=null,timer=null,closed=false,lastRequest=0,generation=0;
 function render(){
  const v=view(data);el('state').textContent=v.state;el('state').dataset.state=v.state;
  el('plan').hidden=!v.scenario;for(const id of ['entry','stop','target','rr'])el(id).textContent='—';
  if(v.scenario){const p=v.scenario;el('entry').textContent=num(p.entry_zone.low)+' – '+num(p.entry_zone.high)+' USDT';el('stop').textContent=num(p.stop_loss);el('target').textContent=num(p.take_profit);el('rr').textContent='1 : '+num(p.net_rr)+' после расходов · gross '+num(p.gross_rr);}
  el('freshness').textContent=v.fresh?'Анализ UTC: '+utc(v.generated)+' · действителен до '+utc(v.valid_until):'Свежесть не подтверждена';
  el('price').textContent=v.fresh?'Ориентир: последнее закрытие BTCUSDT 5m '+num(v.frames['5m'].close)+' USDT · '+utc(v.frames['5m'].last_closed_at)+'. Перед ручным входом проверьте LIVE-цену и спред.':'LIVE-график работает отдельно; устаревший план не используется.';
  el('reasons').replaceChildren();for(const text of v.reasons){const li=d.createElement('li');li.textContent=text;el('reasons').append(li);}
  el('frames').replaceChildren();for(const tf of Object.keys(STEPS)){const f=v.frames[tf],a=d.createElement('article'),h=d.createElement('h3');h.textContent=tf+' · '+(f?f.trend:'WAIT');a.append(h);const dl=d.createElement('dl');for(const [k,label]of [['rsi','RSI 14'],['ema20','EMA 20'],['ema50','EMA 50'],['atr','ATR 14']]){const row=d.createElement('div'),dt=d.createElement('dt'),dd=d.createElement('dd');dt.textContent=label;dd.textContent=f?num(f[k]):'—';row.append(dt,dd);dl.append(row);}a.append(dl);const at=d.createElement('small');at.textContent=f?'Закрытие '+utc(f.last_closed_at):'Нет проверенной истории';a.append(at);el('frames').append(a);}
  el('fib').textContent=v.fibonacci?('Прошлый диапазон '+num(v.fibonacci.low)+' – '+num(v.fibonacci.high)+' USDT\n'+Object.entries(v.fibonacci.levels).map(([k,n])=>num(Number(k)*100)+'%: '+num(n)).join('\n')):'Нет подтверждённого прошлого импульса.';
 }
 async function refresh(){
  if(busy||closed||d.hidden)return;const run=++generation;busy=true;lastRequest=Date.now();el('refresh').disabled=true;data=null;render();controller=new AbortController();const own=controller,timeout=setTimeout(()=>own.abort(),40000);
  try{const r=await root.fetch('/api/analyst',{method:'GET',credentials:'omit',cache:'no-store',redirect:'error',signal:own.signal});if(!r.ok)throw Error('UNAVAILABLE');const b=await r.json();if(!closed&&run===generation){data=b;render();}}
  catch{if(run===generation){data=null;if(!closed)render();}}
  finally{clearTimeout(timeout);if(run===generation){controller=null;busy=false;if(!closed)el('refresh').disabled=false;}}
 }
 function start(){if(timer!==null)clearInterval(timer);timer=setInterval(()=>{render();if(!d.hidden&&Date.now()-lastRequest>=60000)refresh();},1000);}
 el('refresh').addEventListener('click',refresh);
 d.addEventListener('visibilitychange',()=>{if(d.hidden){generation++;controller?.abort();busy=false;el('refresh').disabled=false;data=null;render();}else refresh();});
 root.addEventListener('pagehide',()=>{closed=true;generation++;busy=false;el('refresh').disabled=false;controller?.abort();clearInterval(timer);timer=null;data=null;render();});
 root.addEventListener('pageshow',e=>{if(e.persisted){closed=false;start();refresh();}});
 render();start();refresh();
})(typeof window==='undefined'?globalThis:window);

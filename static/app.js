'use strict';
const $ = id => document.getElementById(id);
const fmt = (value, digits = 2) => Number(value).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits});
const utc = time => new Date(time * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
let timeframe = '15m', chart, candles, ema20, ema50, volume;
let controller, requestId = 0, currentData = null;
const metricIds = ['price','rsi','atr','return','volatility','momentum','count','up','down','headline-price','ema20-value','ema50-value'];

function initializeChart() {
  if (!window.LightweightCharts) throw new Error('Не удалось загрузить библиотеку графика. Проверьте установку зависимостей.');
  const L = window.LightweightCharts;
  chart = L.createChart($('chart'), {
    autoSize: true, layout: {background: {color: '#111720'}, textColor: '#93a1b4', attributionLogo: true},
    grid: {vertLines: {color: '#1b243080'}, horzLines: {color: '#222c3980'}},
    rightPriceScale: {borderColor: '#283241', scaleMargins: {top: .08, bottom: .22}},
    timeScale: {borderColor: '#283241', timeVisible: true, secondsVisible: false, rightOffset: 6},
    crosshair: {mode: L.CrosshairMode.Normal}, localization: {locale: 'en-US'},
  });
  candles = chart.addSeries(L.CandlestickSeries, {upColor: '#42d6b0', downColor: '#fa788b', borderVisible: false, wickUpColor: '#42d6b0', wickDownColor: '#fa788b'});
  ema20 = chart.addSeries(L.LineSeries, {color: '#42d6b0', lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false});
  ema50 = chart.addSeries(L.LineSeries, {color: '#a295fa', lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false});
  volume = chart.addSeries(L.HistogramSeries, {priceFormat: {type: 'volume'}, priceScaleId: 'volume', lastValueVisible: false, priceLineVisible: false});
  volume.priceScale().applyOptions({scaleMargins: {top: .86, bottom: 0}});
  try {
    window.AuraChartTools?.attach({chart, series:candles, getContext:()=>({symbol:$('symbol').value,timeframe,candles:currentData?.candles||[]})});
  } catch (_) {
    // Optional manual tools must never prevent the existing LIVE chart loading.
    const status = document.getElementById('drawing-status');
    if (status) status.textContent = 'Ручные инструменты недоступны. LIVE-график работает отдельно; сделки не создаются.';
  }
  chart.subscribeCrosshairMove(param => {
    const c = param.seriesData.get(candles);
    if (!c) { $('ohlcv').textContent = 'Наведите курсор на свечу для просмотра OHLCV'; return; }
    const v = param.seriesData.get(volume);
    $('ohlcv').textContent = `${utc(c.time)}  O ${fmt(c.open)}  H ${fmt(c.high)}  L ${fmt(c.low)}  C ${fmt(c.close)}  V ${v?.value == null ? '—' : fmt(v.value)}`;
  });
}

function clearData() {
  currentData = null;
  window.AuraChartTools?.refresh?.();
  metricIds.forEach(id => { $(id).textContent = '—'; $(id).classList.remove('positive', 'negative'); });
  $('trend').textContent = '—'; $('trend').className = 'trend';
  $('headline-return').textContent = '— за выборку'; $('headline-return').className = '';
  $('up-bar').style.width = '0'; $('down-bar').style.width = '0';
  $('source').textContent = 'Источник —'; $('last-updated').textContent = 'Данные ещё не загружены';
  $('factor-values').textContent = 'Вклад факторов появится после загрузки.';
  $('ohlcv').textContent = 'Наведите курсор на свечу для просмотра OHLCV';
  if (chart) [candles, ema20, ema50, volume].forEach(series => series.setData([]));
}

function signed(id, value, suffix = '%') {
  $(id).textContent = (value > 0 ? '+' : '') + fmt(value) + suffix;
  $(id).className = value > 0 ? 'positive' : value < 0 ? 'negative' : '';
}

async function loadMarket() {
  if (document.body.dataset.liveManual === "true") {
    stopMarketLive(); clearData(); $("limit").disabled=true; $("limit").options[0].text="200 + формирующаяся"; if (!chart) initializeChart();
    $("chart-subtitle").textContent="Bitget USDT-M Futures · "+timeframe+" · LIVE";
    $("chart-overlay").hidden=false; $("chart-overlay").textContent="Восстановление публичного LIVE-потока…";
    window.dispatchEvent(new CustomEvent("aura-manual-chart-frame",{detail:timeframe}));
    return;
  }
  stopMarketLive();
  controller?.abort();
  controller = new AbortController();
  const signal = controller.signal, id = ++requestId;
  const symbol = $('symbol').value, limit = $('limit').value;
  clearData();
  $('chart-title').textContent = symbol === 'BTCUSDT' ? 'BTC / USDT' : 'XAU / USD';
  $('chart-subtitle').textContent = (symbol === 'BTCUSDT' ? 'Bitcoin · Bitget USDT-M Futures' : 'Gold · BID') + ' · ' + timeframe;
  $('status').className = 'status';
  $('status').textContent = symbol === 'XAUUSD' ? 'Загружаем архив золота. Первый запрос может занять до 100 секунд…' : 'Загружаем историю Bitget Futures…';
  $('chart-overlay').hidden = false; $('chart-overlay').textContent = 'Загружаем свечи…';
  $('refresh').disabled = true;
  const timeout = setTimeout(() => controller?.signal === signal && controller.abort(), 110000);
  try {
    if (!chart) initializeChart();
    const response = await fetch(`/api/market?symbol=${symbol}&timeframe=${timeframe}&limit=${limit}`, {signal});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Ошибка запроса данных.');
    if (id !== requestId) return;
    const a = data.analysis;
    candles.setData(data.candles);
    ema20.setData(a.series.ema20); ema50.setData(a.series.ema50);
    volume.setData(data.candles.filter(c => c.volume != null).map(c => ({time: c.time, value: c.volume, color: c.close >= c.open ? '#42d6b030' : '#fa788b30'})));
    chart.timeScale().setVisibleLogicalRange({from: Math.max(0, data.candles.length - 120), to: data.candles.length + 4});
    currentData = data;
    lastLiveReceipt = Date.now(); liveMode = 'history'; lastSourceEvent = null;
    marketDataChanged();
    $('chart-overlay').hidden = true;
    $('headline-price').textContent = fmt(a.price);
    signed('headline-return', a.return_pct, '% за выборку');
    $('price').textContent = fmt(a.price) + (symbol === 'BTCUSDT' ? ' USDT' : ' USD');
    $('rsi').textContent = fmt(a.rsi); $('atr').textContent = fmt(a.atr);
    $('ema20-value').textContent = fmt(a.ema20); $('ema50-value').textContent = fmt(a.ema50);
    $('count').textContent = fmt(a.count, 0);
    $('up').textContent = fmt(a.signal_up, 1) + '%'; $('down').textContent = fmt(a.signal_down, 1) + '%';
    $('up-bar').style.width = a.signal_up + '%'; $('down-bar').style.width = a.signal_down + '%';
    $('trend').textContent = a.trend; $('trend').className = 'trend ' + a.trend.toLowerCase();
    signed('return', a.return_pct); signed('momentum', a.momentum_pct);
    $('volatility').textContent = fmt(a.volatility_pct, 3) + '%';
    $('source').textContent = data.source;
    if (symbol === 'XAUUSD') $('chart-subtitle').textContent = 'Gold · ' + timeframe + ' · ' + data.source;
    $('status').className = 'status' + (data.stale ? ' warning' : '');
    $('status').textContent = `${data.stale ? 'Задержка / рынок закрыт · ' : ''}Последнее закрытие: ${utc(data.last_closed_at)}. ${data.note}`;
    if (data.fallback) {
      $('status').className = 'status warning';
      $('status').textContent = `Fallback · Dukascopy: ${data.fallback_reason}. ` + $('status').textContent;
    }
    $('last-updated').textContent = 'Получено: ' + utc(new Date(data.fetched_at).getTime() / 1000);
    $('factor-values').textContent = `Вклад: EMA ${fmt(a.factors.ema, 3)}, RSI ${fmt(a.factors.rsi, 3)}, momentum ${fmt(a.factors.momentum, 3)}. D = ${fmt(a.damping, 3)}.`;
    if (data.stale) invalidateMarketSignal('История устарела; сигнал отключён.');
    startMarketLive(id, symbol, timeframe, limit);
    return {symbol: data.symbol, timeframe: data.timeframe, count: a.count, signal_up: a.signal_up, signal_down: a.signal_down};
  } catch (error) {
    if (id !== requestId) return;
    clearData();
    $('status').className = 'status error';
    $('status').textContent = error.name === 'AbortError' ? 'Превышено время ожидания. Нажмите «Обновить» для повторной загрузки.' : error.message;
    $('chart-overlay').hidden = false; $('chart-overlay').textContent = 'Данные недоступны. Повторите загрузку кнопкой «Обновить».';
    // Live channel can recover independently if the initial REST snapshot failed.
    startMarketLive(id, symbol, timeframe, limit);
    return {error: $('status').textContent};
  } finally {
    clearTimeout(timeout);
    if (id === requestId) $('refresh').disabled = false;
  }
}

function selectTimeframe(value) {
  timeframe = value;
  document.querySelectorAll('[data-tf]').forEach(b => { b.classList.toggle('active', b.dataset.tf === timeframe); b.setAttribute('aria-pressed', String(b.dataset.tf === timeframe)); });
}
$('symbol').addEventListener('change', loadMarket);
$('limit').addEventListener('change', loadMarket);
$('refresh').addEventListener('click', loadMarket);
$('timeframes').addEventListener('click', event => {
  const b = event.target.closest('[data-tf]');
  if (b && b.dataset.tf !== timeframe) { selectTimeframe(b.dataset.tf); loadMarket(); }
});
$('fit').addEventListener('click', () => chart?.timeScale().fitContent());
$('ema20-toggle').addEventListener('change', event => ema20?.applyOptions({visible: event.target.checked}));
$('ema50-toggle').addEventListener('change', event => ema50?.applyOptions({visible: event.target.checked}));
if (document.modelContext?.registerTool) {
  try {
    Promise.resolve(document.modelContext.registerTool({
      name: 'configure_market_analysis', description: 'Выбрать рынок, таймфрейм и глубину, загрузить и показать анализ.',
      inputSchema: {type: 'object', properties: {symbol: {enum: ['BTCUSDT']}, timeframe: {enum: ['1m','5m','15m','1h','4h']}, limit: {enum: [500,2000]}}, required: ['symbol','timeframe','limit'], additionalProperties: false},
      annotations: {readOnlyHint: false, untrustedContentHint: true},
      async execute(input) {
        if (!input || !['BTCUSDT'].includes(input.symbol) || !['1m','5m','15m','1h','4h'].includes(input.timeframe) || ![500,2000].includes(input.limit)) throw new Error('Invalid market parameters');
        $('symbol').value = input.symbol; $('limit').value = String(input.limit); selectTimeframe(input.timeframe);
        return await loadMarket();
      }
    })).catch(() => {});
  } catch (_) { /* Optional browser API. */ }
}
loadMarket();

// Browser-only public feed, never an execution price or Active43 input.
let manualChartFrame=null,manualPriceLines=[];
window.addEventListener('aura-manual-market',event=>{
 if(document.body.dataset.liveManual!=='true')return;
 const snapshot=event.detail,now=Date.now()/1000,w=snapshot?.windows?.[timeframe];
 const fresh=snapshot?.status==='LIVE'&&window.AuraManualLiveAnalysis?.quoteFresh(snapshot.quote,now);
 $('feed-state').textContent=fresh?'LIVE':w?.bars?.length?'HISTORY ONLY · '+(snapshot?.status||'STALE'):snapshot?.status||'STALE';
 if(!w?.bars?.length){
  // Keep the last integrity-checked candles visible on transient reconnects.
  const hasHistory=Boolean(currentData?.candles?.length);
  $('chart-overlay').hidden=hasHistory;
  if(!hasHistory)$('chart-overlay').textContent='STALE · подтверждённой истории пока нет';
  $('status').className='status warning';
  $('status').textContent='Нет свежих котировок. История'+(hasHistory?' сохранена на экране.':' ещё не загружена.')+' Рекомендации заблокированы.';
  $('event-age').textContent='Bid/Ask не подтверждены';
  if(!hasHistory)$('headline-price').textContent='—';
  return;
 }
 if(!chart)initializeChart();
 try{
  const step=window.AuraManualLiveAnalysis.STEPS[timeframe];
  const closed=window.AuraManualLiveAnalysis.windowCheck(w.bars,step,now);
  const bars=fresh?w.bars:closed; // Never display forming candles as current without verified bid/ask.
  currentData={symbol:'BTCUSDT',timeframe,candles:bars};
  candles.setData(bars);ema20.setData(window.AuraBitgetLive.ema(bars,20));ema50.setData(window.AuraBitgetLive.ema(bars,50));
  volume.setData(bars.map(b=>({time:b.time,value:b.volume,color:b.close>=b.open?'#42d6b055':'#fa788b55'})));
  if(manualChartFrame!==timeframe){chart.timeScale().setVisibleLogicalRange({from:Math.max(0,bars.length-100),to:bars.length+4});manualChartFrame=timeframe;}
  $('chart-overlay').hidden=true;
  if(fresh){
   $('headline-price').textContent=fmt(snapshot.quote.last);$('price').textContent=fmt(snapshot.quote.last);
   $('headline-return').textContent='текущая котировка Bitget';
   $('event-age').textContent='Возраст котировки '+Math.max(0,now-snapshot.quote.time).toFixed(1)+' с';
   $('source').textContent='Bitget USDT-M Futures · публичный WebSocket';
   $('live-candle').textContent='Формируется '+timeframe+' · '+utc(w.bars.at(-1).time)+' · V '+fmt(w.bars.at(-1).volume);
   $('status').className='status';
   $('status').textContent='LIVE: текущая свеча предварительная; закрытые подтверждения в AURA ANALYST.';
   const m=window.AuraManualLiveAnalysis.metrics(bars);
   for(const [id,key]of [['ema20-value','ema20'],['ema50-value','ema50'],['rsi','rsi'],['atr','atr']])$(id).textContent=fmt(m[key]);
   $('trend').textContent=m.trend+' · предварительно';
   document.dispatchEvent(new CustomEvent('market-data-changed'));
  }else{
   const last=closed.at(-1);
   $('headline-price').textContent=fmt(last.close);
   $('headline-return').textContent='последнее закрытие · НЕ LIVE';
   $('price').textContent='— (нет свежей котировки)';
   $('event-age').textContent='Bid/Ask не подтверждены';
   $('source').textContent='Bitget USDT-M Futures · проверенная история · НЕ LIVE';
   $('live-candle').textContent='Последняя закрытая '+timeframe+' · '+utc(last.time)+' · C '+fmt(last.close);
   $('status').className='status warning';
   $('status').textContent='HISTORY ONLY: показаны только закрытые свечи. Нет свежего LIVE-потока; сигналы и входы заблокированы.';
   $('trend').textContent='— (нет LIVE)';
  }
  $('last-updated').textContent=fresh?'Последнее получение UTC: '+utc(w.received_at):'История загружена · нет подтверждённой свежей котировки';
  $('count').textContent=bars.length;
  window.AuraChartTools?.refresh?.();
 }catch(error){
  $('chart-overlay').hidden=false;
  $('chart-overlay').textContent='История не прошла проверку: '+String(error?.message||'INVALID_HISTORY').slice(0,90);
  $('status').className='status warning';
  $('status').textContent='История отклонена, торговые сигналы заблокированы.';
 }
});
window.addEventListener('aura-manual-position',event=>{
 if(!candles)return;for(const line of manualPriceLines)candles.removePriceLine(line);manualPriceLines=[];
 const p=event.detail;if(!p)return;
 for(const [key,title,color]of [['entry','Manual Entry','#f4c779'],['stop','Manual SL','#fa788b'],['target','Manual TP','#42d6b0']]){
  const price=Number(p[key]);if(Number.isFinite(price)&&price>0)manualPriceLines.push(candles.createPriceLine({price,title,color,lineWidth:2}));
 }
});
let manualMarkers=null,manualTrades=[];
function drawManualHistory(){
 if(!candles||!currentData?.candles?.length||!window.LightweightCharts.createSeriesMarkers)return;
 const step=window.AuraManualLiveAnalysis?.STEPS[timeframe];if(!step)return;
 const first=currentData.candles[0].time,last=currentData.candles.at(-1).time,marks=[];
 for(const t of manualTrades){
  for(const [key,exit]of [['opened_at',false],['closed_at',true]]){
   const at=Number(t[key]);if(!Number.isFinite(at)||at<=0)continue;
   const time=Math.floor(at/1000/step)*step;if(time<first||time>last)continue;
   marks.push({time,position:exit?'aboveBar':t.side==='LONG'?'belowBar':'aboveBar',color:exit?'#f4c779':t.side==='LONG'?'#42d6b0':'#fa788b',shape:exit?'circle':t.side==='LONG'?'arrowUp':'arrowDown',text:(exit?'CLOSE':'OPEN '+t.side)+' · Manual Paper'});
  }
 }
 marks.sort((a,b)=>a.time-b.time);if(!manualMarkers)manualMarkers=window.LightweightCharts.createSeriesMarkers(candles,marks);else manualMarkers.setMarkers(marks);
}
window.addEventListener('aura-manual-history',event=>{manualTrades=Array.isArray(event.detail)?event.detail:[];drawManualHistory();});
window.addEventListener('aura-manual-market',drawManualHistory);

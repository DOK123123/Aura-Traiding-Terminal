'use strict';
let marketSocket = null, retryTimer = null, retryDelay = 2000;
let lastLiveReceipt = 0, liveMode = '', lastSourceEvent = null, liveUpdates = 0, feedFailed = false;

function stopMarketLive() {
  clearTimeout(retryTimer);
  if (marketSocket) { marketSocket.onclose = null; marketSocket.close(); marketSocket = null; }
  lastLiveReceipt = 0; liveUpdates = 0; liveMode = ''; feedFailed = false;
  $('live-events').textContent = '0'; $('event-age').textContent = '—';
  $('feed-state').textContent = 'Подключение к обновлениям…';
  $('live-candle').textContent = 'Текущая свеча: ожидаем данные источника';
  retryDelay = 2000;
}

function liveMetrics(data) {
  const a = data.analysis;
  $('headline-price').textContent = fmt(a.price);
  $('price').textContent = fmt(a.price) + (data.symbol === 'BTCUSDT' ? ' USDT' : ' USD');
  $('ema20-value').textContent = fmt(a.ema20); $('ema50-value').textContent = fmt(a.ema50);
  $('rsi').textContent = fmt(a.rsi); $('atr').textContent = fmt(a.atr);
  $('count').textContent = fmt(a.count,0);
  $('up').textContent = fmt(a.signal_up,1)+'%'; $('down').textContent = fmt(a.signal_down,1)+'%';
  $('up-bar').style.width = a.signal_up+'%'; $('down-bar').style.width = a.signal_down+'%';
  $('trend').textContent = a.trend; $('trend').className = 'trend '+a.trend.toLowerCase();
  signed('headline-return',a.return_pct,'% за выборку'); signed('return',a.return_pct); signed('momentum',a.momentum_pct);
  $('volatility').textContent = fmt(a.volatility_pct,3)+'%';
  $('factor-values').textContent = `Вклад: EMA ${fmt(a.factors.ema,3)}, RSI ${fmt(a.factors.rsi,3)}, momentum ${fmt(a.factors.momentum,3)}. D = ${fmt(a.damping,3)}. ${data.current_closed ? 'Последняя свеча закрыта.' : 'Анализ включает текущую незакрытую свечу и может изменяться.'}`;
}

function applyLive(data) {
  const first = !currentData;
  const logical = chart.timeScale().getVisibleLogicalRange();
  const visible = chart.timeScale().getVisibleRange();
  const follow = !currentData || !logical || logical.to >= currentData.candles.length-2;
  if (data.type === 'snapshot' || data.rolled) {
    candles.setData(data.candles);
    ema20.setData(data.analysis.series.ema20); ema50.setData(data.analysis.series.ema50);
    volume.setData(data.candles.filter(c => c.volume != null).map(c => ({time:c.time,value:c.volume,color:c.close>=c.open?'#42d6b030':'#fa788b30'})));
    if (first) chart.timeScale().setVisibleLogicalRange({from:data.candles.length-120,to:data.candles.length+4});
    else if (follow && logical) chart.timeScale().setVisibleLogicalRange(logical);
    else if (visible) chart.timeScale().setVisibleRange(visible);
    currentData = data;
  } else {
    if (!currentData) throw new Error('Missing snapshot');
    const c = data.candle;
    candles.update(c);
    ema20.update(data.analysis.series.ema20.at(-1)); ema50.update(data.analysis.series.ema50.at(-1));
    if (c.volume != null) volume.update({time:c.time,value:c.volume,color:c.close>=c.open?'#42d6b030':'#fa788b30'});
    currentData.candles[currentData.candles.length-1] = c;
    currentData = {...currentData,...data,candles:currentData.candles};
  }
  const c = currentData.candles.at(-1);
  liveMetrics(data);
  $('chart-overlay').hidden = true;
  $('source').textContent = data.source;
  $('chart-subtitle').textContent = `${data.symbol === 'BTCUSDT' ? 'Bitcoin' : 'Gold'} · ${data.timeframe} · ${data.source}`;
  $('status').className = 'status'+(data.mode !== 'streaming' || data.stale ? ' warning' : '');
  $('status').textContent = data.note;
  $('live-candle').textContent = `${data.current_closed ? 'Последняя закрытая' : 'Текущая · предварительная'} ${utc(c.time)} | O ${fmt(c.open)} H ${fmt(c.high)} L ${fmt(c.low)} C ${fmt(c.close)} V ${c.volume == null ? '—' : fmt(c.volume,5)}`;
  $('live-candle').dataset.time = String(c.time);
  $('live-candle').dataset.close = String(c.close);
  $('live-candle').dataset.volume = String(c.volume);
  lastLiveReceipt = Date.now(); lastSourceEvent = data.event_age_seconds; liveMode = data.mode; feedFailed = false;
  liveUpdates++; $('live-events').textContent = String(liveUpdates);
  $('last-updated').textContent = 'Получено: '+new Date(data.received_at*1000).toISOString().replace('T',' ').slice(0,19)+' UTC';
  updateFeedAge();
}

function updateFeedAge() {
  if (!lastLiveReceipt) return;
  const age = Math.max(0,Math.floor((Date.now()-lastLiveReceipt)/1000));
  const quoteAge = lastSourceEvent == null ? null : Math.max(0,Math.floor(lastSourceEvent+age));
  $('event-age').textContent = `Получено ${age} с назад`+(quoteAge == null?' · задержка котировки неизвестна':` · возраст события ${quoteAge} с`);
  if (feedFailed) return;
  const stale = liveMode === 'streaming' ? age > 10 || quoteAge > 10 : age > 60;
  $('feed-state').textContent = stale ? 'Задержка / соединение прервано' :
    liveMode === 'streaming' ? 'LIVE · Binance WebSocket' :
    liveMode === 'source_stream' ? 'STREAM · XAUUSD · задержка источника неизвестна' :
    liveMode === 'polling' ? 'POLLING · 30 с · задержка источника неизвестна' :
    liveMode === 'syncing' ? 'Синхронизация · ожидаем текущую свечу' : 'DELAYED · только закрытые свечи';
}
setInterval(updateFeedAge,1000);

function startMarketLive(id,symbol,tf,limit) {
  if (id !== requestId) return;
  clearTimeout(retryTimer);
  const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/market?symbol=${symbol}&timeframe=${tf}&limit=${limit}`);
  marketSocket = socket;
  socket.onmessage = event => {
    if (id !== requestId || socket !== marketSocket) return;
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'status') {
        feedFailed = true;
        $('feed-state').textContent = 'Нет актуальных обновлений';
        $('status').className = 'status warning'; $('status').textContent = data.message;
        return;
      }
      if (data.symbol !== symbol || data.timeframe !== tf) return;
      applyLive(data); retryDelay = 2000;
    } catch (error) {
      $('status').textContent = 'Ошибка обновления: '+error.message;
      socket.close();
    }
  };
  socket.onclose = () => {
    if (id !== requestId || socket !== marketSocket) return;
    feedFailed = true; $('feed-state').textContent = 'Переподключение · данные заморожены';
    retryTimer = setTimeout(() => startMarketLive(id,symbol,tf,limit),retryDelay);
    retryDelay = Math.min(15000,retryDelay*2);
  };
  socket.onerror = () => socket.close();
}
window.addEventListener('pagehide', () => { clearTimeout(retryTimer); if (marketSocket) {marketSocket.onclose=null; marketSocket.close();} });

// Owner-protected account reads only. Binance credentials never enter the browser.
(() => {
  const el = id => document.getElementById('testnet-' + id);
  const orderKeys = ['orderId', 'symbol', 'side', 'type', 'status', 'price', 'origQty', 'executedQty'];
  let busy = false, historyBusy = false, nextRead = 0, lastFresh = 0, stopped = false, generation = 0;
  const controllers = new Set();
  const utc = value => new Date(value).toISOString().replace('T', ' ').replace('.000Z', ' UTC');

  function table(id, rows, keys, empty) {
    const body = el(id);
    body.replaceChildren();
    if (!rows.length) {
      const row = document.createElement('tr'), cell = document.createElement('td');
      cell.colSpan = keys.length; cell.textContent = empty; row.append(cell); body.append(row);
      return;
    }
    for (const item of rows) {
      const row = document.createElement('tr');
      for (const key of keys) {
        const cell = document.createElement('td');
        cell.textContent = key === 'time' ? utc(item[key]) : String(item[key]);
        row.append(cell);
      }
      body.append(row);
    }
  }
  function clearData() {
    generation++;
    el('data').hidden = el('history').hidden = true;
    for (const id of ['balances', 'orders', 'past-orders', 'trades']) el(id).replaceChildren();
    el('assets').textContent = el('meta').textContent = '';
    lastFresh = 0;
  }
  function state(status, message, login = false) {
    el('state').textContent = status; el('message').textContent = message;
    el('login').hidden = !login;
  }
  async function get(section, query = '') {
    const controller = new AbortController(); controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch('/api/testnet/' + section + query, {
        method: 'GET', credentials: 'same-origin', cache: 'no-store', signal: controller.signal
      });
      if (response.status === 401) return {status: 'Disconnected', login: true,
        message: 'Войдите с именем aura и паролем владельца для просмотра аккаунта.'};
      if (response.status === 403) return {status: 'Disconnected',
        message: 'Просмотр закрыт: настройте AURA_TESTNET_VIEW_PASSWORD в Render (от 12 символов).'};
      if (!response.ok) throw new Error('Account unavailable');
      return await response.json();
    } finally {
      clearTimeout(timeout); controllers.delete(controller);
    }
  }
  async function refresh(force = false) {
    if (busy || stopped || (!force && Date.now() < nextRead)) return;
    busy = true; el('refresh').disabled = true;
    try {
      const data = await get('account');
      if (stopped) return;
      nextRead = Date.now() + Math.max(60000, Number(data.retry_after || 0) * 1000);
      if (data.status !== 'Connected' || data.stale) {
        clearData(); state(data.status || 'Disconnected', data.message || 'Данные Testnet недоступны.', data.login);
        return;
      }
      table('balances', data.balances, ['asset', 'free', 'locked', 'total'], 'Нет тестовых активов.');
      table('orders', data.open_orders, orderKeys, 'Нет открытых тестовых ордеров.');
      el('assets').textContent = 'Активы с доступным балансом: ' + (data.available_assets.join(', ') || 'нет');
      el('meta').textContent = 'Проверено: ' + utc(data.checked_at) + '. Обновление раз в 60 с; это снимок аккаунта, не поток.';
      el('data').hidden = false;
      lastFresh = Date.now() - Math.max(0, Number(data.cache_age_seconds || 0)) * 1000;
      state('Connected', 'Официальный Binance Spot Testnet · только чтение.');
    } catch (_) {
      if (stopped) return;
      clearData(); state('Disconnected', 'Не удалось получить Testnet-аккаунт. Повторим автоматически.');
      nextRead = Date.now() + 60000;
    } finally {
      busy = false; el('refresh').disabled = false;
    }
  }
  async function history() {
    if (historyBusy || el('data').hidden || stopped) return;
    const symbol = el('history-symbol').value;
    if (!/^[A-Z0-9]{5,20}$/.test(symbol)) {
      el('history-status').textContent = 'Укажите пару Testnet, например BTCUSDT или ETHUSDT.';
      return;
    }
    historyBusy = true; el('history-refresh').disabled = true;
    const currentGeneration = generation;
    try {
      const data = await get('history', '?symbol=' + encodeURIComponent(symbol));
      if (stopped || currentGeneration !== generation) return;
      if (data.status !== 'Connected' || data.stale) {
        el('history').hidden = true;
        el('past-orders').replaceChildren(); el('trades').replaceChildren();
        el('history-status').textContent = data.message || 'История недоступна.';
        if (data.login) el('login').hidden = false;
        return;
      }
      table('past-orders', data.orders, [...orderKeys, 'time'], 'Нет истории тестовых ордеров ' + symbol + '.');
      const trades = data.trades.map(row => ({...row, commission: row.commission + ' ' + row.commissionAsset}));
      table('trades', trades, ['id', 'orderId', 'side', 'price', 'qty', 'quoteQty', 'commission', 'time'], 'Нет истории тестовых сделок ' + symbol + '.');
      el('past-orders-title').textContent = 'ИСТОРИЯ ТЕСТОВЫХ ОРДЕРОВ · ' + symbol;
      el('trades-title').textContent = 'ИСТОРИЯ ТЕСТОВЫХ СДЕЛОК · ' + symbol;
      el('history-status').textContent = data.message + ' Проверено: ' + utc(data.checked_at);
      el('history').hidden = false;
    } catch (_) {
      if (stopped) return;
      el('history').hidden = true;
      el('past-orders').replaceChildren(); el('trades').replaceChildren();
      el('history-status').textContent = 'Не удалось прочитать историю. Повторите запрос позже.';
    } finally {
      historyBusy = false; el('history-refresh').disabled = false;
    }
  }
  function expire() {
    if (lastFresh && Date.now() - lastFresh > 90000) {
      clearData(); state('Disconnected', 'Данные аккаунта устарели. Ожидаем повторного чтения.');
    }
  }
  el('refresh').addEventListener('click', () => refresh(true));
  el('history-refresh').addEventListener('click', history);
  const timer = setInterval(() => { expire(); if (!document.hidden) refresh(); }, 5000);
  document.addEventListener('visibilitychange', () => { expire(); if (!document.hidden) refresh(); });
  window.addEventListener('pagehide', () => { stopped = true; clearInterval(timer); controllers.forEach(c => c.abort()); clearData(); });
  window.addEventListener('pageshow', () => { if (stopped) location.reload(); });
  refresh();
})();

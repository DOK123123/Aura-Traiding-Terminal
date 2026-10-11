// Only same-origin, owner-protected Bybit Demo reads; no exchange credentials.
(() => {
  const el = id => document.getElementById('demo-' + id);
  const categories = new Set(['spot', 'linear', 'inverse', 'option']);
  const orderKeys = ['order_id', 'symbol', 'side', 'type', 'status', 'price', 'quantity', 'executed_quantity'];
  const controllers = new Set();
  let busy = false, historyBusy = false, nextRead = 0, lastFresh = 0, stopped = false, generation = 0, pendingRefresh = false;
  const utc = value => new Date(value).toISOString().replace('T', ' ').replace('.000Z', ' UTC');
  const display = value => value === null || value === undefined || value === '' ? '—' : String(value);
  function scope() {
    const symbol = el('symbol').value, category = el('category').value;
    if (!/^[A-Z0-9-]{3,64}$/.test(symbol) || !categories.has(category)) throw new Error('Invalid Demo scope');
    return {symbol, category, query: '?category=' + encodeURIComponent(category) + '&symbol=' + encodeURIComponent(symbol)};
  }
  function table(id, rows, keys, empty) {
    const body = el(id); body.replaceChildren();
    if (!rows.length) {
      const row = document.createElement('tr'), cell = document.createElement('td');
      cell.colSpan = keys.length; cell.textContent = empty; row.append(cell); body.append(row); return;
    }
    for (const item of rows) {
      const row = document.createElement('tr');
      for (const key of keys) {
        const cell = document.createElement('td');
        cell.textContent = key === 'time' ? utc(item[key]) : display(item[key]); row.append(cell);
      }
      body.append(row);
    }
  }
  function clearData() {
    generation++; lastFresh = 0;
    el('data').hidden = el('history').hidden = true;
    for (const id of ['balances', 'orders', 'past-orders', 'trades']) el(id).replaceChildren();
    for (const id of ['assets', 'meta', 'summary', 'history-status']) el(id).textContent = '';
  }
  function state(status, message, login = false) {
    el('state').textContent = status; el('message').textContent = message; el('login').hidden = !login;
  }
  function valid(data, selected) {
    return data.provider === 'BYBIT_DEMO' && data.demo === true && data.read_only === true &&
      data.virtual_funds === true && data.real_money === false && data.symbol === selected.symbol && data.category === selected.category;
  }
  async function get(section, query) {
    const controller = new AbortController(); controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch('/api/bybit-demo/' + section + query, {
        method: 'GET', credentials: 'same-origin', cache: 'no-store', signal: controller.signal
      });
      if (response.status === 401) return {status: 'Disconnected', login: true,
        message: 'Войдите с именем aura и паролем владельца для просмотра Demo.'};
      if (response.status === 403) return {status: 'Disconnected',
        message: 'Просмотр закрыт: настройте AURA_TESTNET_VIEW_PASSWORD в Render (от 12 символов).'};
      if (!response.ok) throw new Error('Demo unavailable');
      return await response.json();
    } finally {
      clearTimeout(timeout); controllers.delete(controller);
    }
  }
  async function refresh(force = false) {
    if (stopped || (!force && Date.now() < nextRead)) return;
    if (busy) { if (force) pendingRefresh = true; return; }
    busy = true; el('refresh').disabled = true;
    const currentGeneration = generation;
    try {
      const selected = scope(), data = await get('account', selected.query);
      if (stopped || currentGeneration !== generation) return;
      nextRead = Date.now() + Math.max(60000, Number(data.retry_after || 0) * 1000);
      if (data.status !== 'Connected' || data.stale) {
        clearData(); state(data.status || 'Disconnected', data.message || 'Bybit Demo недоступен.', data.login); return;
      }
      if (!valid(data, selected)) throw new Error('Demo identity mismatch');
      table('balances', data.balances, ['asset', 'wallet_balance', 'equity', 'locked', 'usd_value', 'spot_borrow'], 'Нет Demo активов.');
      table('orders', data.open_orders, orderKeys, 'Нет открытых Demo ордеров выбранной категории/пары.');
      el('orders-title').textContent = 'OPEN ORDERS · ' + data.open_orders_scope + (data.open_orders_has_more ? ' · СПИСОК ОГРАНИЧЕН' : '');
      el('assets').textContent = 'Активы с положительным wallet balance: ' + (data.available_assets.join(', ') || 'нет');
      const balance = data.demo_balance;
      el('summary').textContent = 'Demo wallet (USD): ' + display(balance.wallet_balance_usd) +
        ' · Equity (USD): ' + display(balance.equity_usd) + ' · Available margin (USD): ' + display(balance.available_balance_usd);
      el('meta').textContent = 'UNIFIED · Проверено: ' + utc(data.checked_at) + '. Снимок раз в 60 с; не поток. VIRTUAL FUNDS · REAL MONEY IS NOT USED.';
      el('data').hidden = false;
      lastFresh = Date.now() - Math.max(0, Number(data.cache_age_seconds || 0)) * 1000;
      state('Connected', 'BYBIT DEMO / READ ONLY · VIRTUAL FUNDS · REAL MONEY IS NOT USED');
    } catch (_) {
      if (stopped || currentGeneration !== generation) return;
      clearData(); state('Disconnected', 'Не удалось получить корректный Bybit Demo снимок. Проверьте категорию/пару; повторим автоматически.');
      nextRead = Date.now() + 60000;
    } finally {
      busy = false; el('refresh').disabled = false;
      if (pendingRefresh && !stopped) { pendingRefresh = false; refresh(true); }
    }
  }
  async function history() {
    if (historyBusy || el('data').hidden || stopped) return;
    historyBusy = true; el('history-refresh').disabled = true;
    const currentGeneration = generation;
    try {
      const selected = scope(), data = await get('history', selected.query);
      if (stopped || currentGeneration !== generation) return;
      if (data.status !== 'Connected' || data.stale) {
        nextRead = Date.now() + Math.max(60000, Number(data.retry_after || 0) * 1000);
        clearData(); state(data.status || 'Disconnected', data.message || 'История Demo недоступна.', data.login); return;
      }
      if (!valid(data, selected)) throw new Error('Demo identity mismatch');
      table('past-orders', data.orders, [...orderKeys, 'time'], 'Нет истории Demo ордеров.');
      const trades = data.trades.map(row => ({...row, commission: row.fee === null ? '—' : display(row.fee) + (row.fee_asset ? ' ' + row.fee_asset : '')}));
      table('trades', trades, ['id', 'order_id', 'side', 'exec_type', 'price', 'quantity', 'value', 'commission', 'time'], 'Нет Demo исполнений.');
      const label = selected.category.toUpperCase() + ' / ' + selected.symbol;
      el('past-orders-title').textContent = 'ORDER HISTORY · ' + label;
      el('trades-title').textContent = 'TRADE HISTORY · ' + label;
      el('history-status').textContent = data.message + (data.orders_has_more || data.trades_has_more ? ' СПИСОК ОГРАНИЧЕН: есть дополнительные записи.' : '') + ' Проверено: ' + utc(data.checked_at);
      el('history').hidden = false;
    } catch (_) {
      if (stopped || currentGeneration !== generation) return;
      el('history').hidden = true;
      el('past-orders').replaceChildren(); el('trades').replaceChildren();
      el('history-status').textContent = 'Не удалось прочитать корректную Demo историю. Повторите позже.';
    } finally {
      historyBusy = false; el('history-refresh').disabled = false;
    }
  }
  function expire() {
    if (lastFresh && Date.now() - lastFresh > 90000) {
      clearData(); state('Disconnected', 'Данные Demo устарели. Ожидаем повторного чтения.');
    }
  }
  function changeScope() {
    controllers.forEach(controller => controller.abort()); clearData(); nextRead = 0;
    state('Disconnected', 'Обновляем выбранную категорию/пару Demo.'); refresh(true);
  }
  el('category').addEventListener('change', changeScope); el('symbol').addEventListener('change', changeScope);
  el('refresh').addEventListener('click', () => refresh(true)); el('history-refresh').addEventListener('click', history);
  const timer = setInterval(() => { expire(); if (!document.hidden) refresh(); }, 5000);
  document.addEventListener('visibilitychange', () => { expire(); if (!document.hidden) refresh(); });
  window.addEventListener('pagehide', () => { stopped = true; clearInterval(timer); controllers.forEach(controller => controller.abort()); clearData(); });
  window.addEventListener('pageshow', () => { if (stopped) location.reload(); });
  refresh();
})();

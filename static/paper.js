// Owner-only LOCAL virtual ledger. No exchange API, keys or automatic signal execution.
(() => {
  const el = id => document.getElementById('paper-' + id);
  const fields = () => Array.from(document.querySelectorAll('[data-paper-setting]'));
  let quote = null, busy = false, loaded = false, pending = null, timer = null;
  const pendingKey = 'aura.paper.pending.v1';
  try {
    const stored = sessionStorage.getItem(pendingKey);
    if (stored) {
      const action = JSON.parse(stored);
      if (!action || !action.body || !/^[0-9a-f-]{36}$/.test(action.body.request_id) ||
          !/^positions\/(?:open|[0-9a-f-]{36}\/close)$/.test(action.path)) throw new Error('Invalid pending action');
      pending = action;
    }
  } catch (_) { try { sessionStorage.removeItem(pendingKey); } catch (_) {} }
  function retainPending() {
    try { if (pending) sessionStorage.setItem(pendingKey,JSON.stringify(pending)); else sessionStorage.removeItem(pendingKey); } catch (_) {}
  }
  const display = v => v === null || v === undefined ? '—' : String(v);
  const status = message => { el('status').textContent = message; };
  function scope() {
    const data = typeof currentData === 'undefined' ? null : currentData;
    const selected = document.querySelector('[data-tf][aria-pressed="true"]');
    const symbol = document.getElementById('symbol').value, timeframe = selected ? selected.dataset.tf : '';
    return {symbol, timeframe, source: data && data.source,
      fresh: Boolean(data && data.symbol === symbol && data.timeframe === timeframe && typeof marketIsFresh === 'function' && marketIsFresh())};
  }
  function matched() {
    const s = scope();
    return Boolean(quote && loaded && !busy && s.fresh && s.symbol === 'BTCUSDT' && quote.symbol === s.symbol &&
      quote.timeframe === s.timeframe && quote.source === s.source && Date.now()-quote.observed_at <= 30000 && quote.observed_at <= Date.now()+1000);
  }
  function buttons() {
    el('open').disabled = !matched() || Boolean(pending);
    for (const id of ['refresh','save','quote-refresh']) el(id).disabled = busy || Boolean(pending);
    el('retry').hidden = !pending; el('retry').disabled = busy;
    for (const button of el('positions').querySelectorAll('button')) button.disabled = busy || Boolean(pending);
  }
  function invalidate() { quote = null; el('quote').textContent = 'Получите новую paper quote.'; buttons(); }
  async function request(path, body) {
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 35000);
    try {
      const options = {credentials:'same-origin', cache:'no-store', signal:controller.signal};
      if (body !== undefined) { options.method = 'POST'; options.headers = {'Content-Type':'application/json','X-Aura-Paper':'local-only'}; options.body = JSON.stringify(body); }
      const response = await fetch('/api/paper/' + path, options);
      el('login').hidden = response.status !== 401;
      if (response.status === 401 || response.status === 403) throw Object.assign(new Error('Paper закрыт. Войдите как aura; пароль — AURA_TESTNET_VIEW_PASSWORD.'),{definitive:true});
      const result = await response.json();
      if (!response.ok) throw Object.assign(new Error(result.message || 'Paper запрос отклонён.'),{definitive:response.status >= 400 && response.status < 500});
      return result;
    } finally { clearTimeout(timeout); }
  }
  function safety(data) {
    if (data.paper !== true || data.real_money_execution !== 'DISABLED' || data.automatic_signal_execution !== false)
      throw new Error('Некорректное состояние safety boundary. Paper действия отключены.');
  }
  function cells(body, values) {
    const row = document.createElement('tr');
    for (const value of values) { const cell = document.createElement('td'); cell.textContent = display(value); row.append(cell); }
    body.append(row); return row;
  }
  function renderCurve(data) {
    const svg = el('curve'); svg.replaceChildren();
    // Conversion to Number is for drawing only; backend ledger uses Decimal strings.
    const points = data.equity_curve, finite = points.filter(p => p.equity !== null && Number.isFinite(Number(p.equity)));
    el('curve-note').textContent = `${points.length} / ${data.equity_curve_total} точек · gaps = нет свежей оценки · max drawdown: sampled liquidation equity.`;
    if (!finite.length) return;
    const values = finite.map(p => Number(p.equity)), lo = Math.min(...values), hi = Math.max(...values), range = hi-lo || 1;
    let segment = [];
    function flush() {
      if (!segment.length) return;
      const line = document.createElementNS('http://www.w3.org/2000/svg','polyline');
      line.setAttribute('class','paper-line'); line.setAttribute('points',segment.join(' ')); svg.append(line); segment = [];
    }
    points.forEach((p,i) => {
      if (p.equity === null || !Number.isFinite(Number(p.equity))) { flush(); return; }
      segment.push(`${10+i*580/Math.max(1,points.length-1)},${145-(Number(p.equity)-lo)*130/range}`);
    }); flush();
  }
  function render(data) {
    safety(data);
    if (!data.statistics || !Array.isArray(data.open_positions) || !Array.isArray(data.closed_trades) || !Array.isArray(data.equity_curve)) throw new Error('Некорректные данные Paper.');
    loaded = true; el('data').hidden = false;
    el('storage').textContent = 'Журнал SQLite. На Render без persistent disk он теряется при restart/redeploy. Скачивайте резервные копии; для постоянного хранения настройте PAPER_DB_PATH на диск.';
    const s = data.statistics, metrics = el('metrics'); metrics.replaceChildren();
    for (const [name,value] of [['Virtual Balance',s.current_balance],['Equity',s.equity],['Realized PnL',s.net_pnl],['Win Rate %',s.win_rate],['Profit Factor',s.profit_factor],['Max Drawdown %',s.maximum_drawdown_pct],['Open Positions',s.open_positions],['Closed Trades',s.total_trades],['Available USDT',s.available_balance],['Return %',s.return_pct],['Gross Profit',s.gross_profit],['Gross Loss',s.gross_loss],['Avg Win / Loss',`${display(s.average_win)} / ${display(s.average_loss)}`],['Planned Risk/Reward',s.risk_reward],['Win / Loss Streak',`${s.consecutive_wins} / ${s.consecutive_losses}`],['Fees USDT',s.total_commissions]]) {
      const card = document.createElement('div'), label = document.createElement('span'), valueNode = document.createElement('strong');
      label.textContent = name; valueNode.textContent = display(value); card.append(label,valueNode); metrics.append(card);
    }
    for (const input of fields()) if (document.activeElement !== input) {
      input.value = data.settings[input.dataset.paperSetting];
      input.disabled = input.dataset.paperSetting === 'starting_balance' && (s.total_trades+s.open_positions > 0);
    }
    el('positions').replaceChildren();
    for (const trade of data.open_positions) {
      const row = cells(el('positions'),[trade.symbol+' / '+trade.direction,trade.entry_price,trade.position_size,trade.stop_loss,trade.take_profit,trade.unrealized_pnl,trade.data_status]);
      const cell = document.createElement('td'), button = document.createElement('button'); button.textContent = 'Close Paper';
      button.addEventListener('click',() => close(trade)); cell.append(button); row.append(cell);
    }
    if (!data.open_positions.length) cells(el('positions'),['Нет открытых paper positions']);
    el('trades').replaceChildren();
    for (const t of data.closed_trades) cells(el('trades'),[new Date(t.exit_time).toISOString(),t.symbol+' / '+t.direction,t.entry_price,t.exit_price,t.position_size,t.commissions,t.realized_pnl,t.pnl_pct,t.entry_reason,t.exit_reason,t.source+' / '+t.timeframe]);
    if (!data.closed_trades.length) cells(el('trades'),['Нет закрытых paper trades']);
    el('journal-note').textContent = `Показано ${data.closed_trades.length} из ${data.closed_trades_total}; полный архив — SQLite backup. Gross profit/loss агрегируют net исходы после комиссий. Profit Factor без убытков = —.`;
    renderCurve(data); buttons();
  }
  function fail(error) { status(error.message || 'Paper временно недоступен.'); loaded = false; el('data').hidden = true; invalidate(); }
  async function refresh() {
    if (busy || pending) return;
    busy = true; buttons();
    try { render(await request('state')); status('PAPER ONLY · manual entry · protective SL/TP · AUTO ENTRY OFF'); }
    catch(error) { fail(error); }
    finally { busy = false; buttons(); }
  }
  async function getQuote() {
    if (busy || pending) return;
    const before = scope();
    if (!before.fresh || before.symbol !== 'BTCUSDT' || !before.source) { status('Нужен свежий график BTCUSDT.'); invalidate(); return; }
    busy = true; buttons();
    try {
      const result = await request('quote?symbol=BTCUSDT&timeframe='+encodeURIComponent(before.timeframe)); safety(result);
      const after = scope();
      if (!after.fresh || after.symbol !== before.symbol || after.timeframe !== before.timeframe || result.source !== after.source) throw new Error('График изменился или источник не совпадает.');
      quote = result; el('quote').textContent = `${result.price} USDT · ${result.source} · ${result.timeframe} · closed ${new Date(result.price_time).toISOString()}`;
      status('Quote подтверждена. Виртуальное исполнение по closed candle close.');
    } catch(error) { invalidate(); status(error.message); }
    finally { busy = false; buttons(); }
  }
  async function execute() {
    if (!pending || busy) return;
    busy = true; buttons();
    try { await request(pending.path,pending.body); pending = null; invalidate(); render(await request('state')); status('Paper action выполнено. Биржевые ордера не отправлялись.'); }
    catch(error) {
      if (error.definitive) { pending = null; invalidate(); }
      status(error.message + (pending ? ' Исход неизвестен: повторите с тем же request ID; не открывайте новую сделку.' : ''));
    } finally { retainPending(); busy = false; buttons(); }
  }
  function open() {
    if (!matched() || pending) return;
    const reason = el('reason').value.trim(); if (!reason) { status('Укажите причину входа.'); return; }
    pending = {path:'positions/open',body:{request_id:crypto.randomUUID(),symbol:quote.symbol,timeframe:quote.timeframe,direction:el('direction').value,
      expected_source:quote.source,expected_candle_time:quote.candle_time,expected_price:quote.price,entry_reason:reason,
      position_size:el('size').value.trim() || null,stop_loss:el('stop').value.trim() || null,take_profit:el('target').value.trim() || null,signal_id:null}};
    retainPending(); execute();
  }
  function close(trade) {
    if (busy || pending) return;
    pending = {path:'positions/'+encodeURIComponent(trade.id)+'/close',body:{request_id:crypto.randomUUID(),exit_reason:'Ручное закрытие владельцем'}};
    retainPending(); execute();
  }
  async function save() {
    if (busy || pending) return;
    const values = Object.fromEntries(fields().map(i => [i.dataset.paperSetting,i.dataset.paperSetting === 'maximum_simultaneous_positions' ? Number(i.value) : i.value.trim()]));
    busy = true; buttons();
    try { await request('settings',values); render(await request('state')); status('Paper настройки сохранены. Открытые позиции не изменены.'); invalidate(); }
    catch(error) { status(error.message); }
    finally { busy = false; buttons(); }
  }
  el('refresh').addEventListener('click',refresh); el('quote-refresh').addEventListener('click',getQuote);
  el('open').addEventListener('click',open); el('save').addEventListener('click',save); el('retry').addEventListener('click',execute);
  document.getElementById('symbol').addEventListener('change',invalidate);
  document.getElementById('timeframes').addEventListener('click',invalidate);
  document.addEventListener('market-unavailable',invalidate);
  document.addEventListener('market-data-changed',buttons);
  timer = setInterval(() => { buttons(); if (!document.hidden) refresh(); },15000);
  window.addEventListener('pagehide',() => { clearInterval(timer); });
  if (pending) { status('Есть неподтверждённое paper действие. Повторите его с прежним request ID.'); buttons(); }
  else refresh();
})();

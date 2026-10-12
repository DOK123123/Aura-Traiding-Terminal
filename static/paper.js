// Owner-only LOCAL virtual ledger; explicit virtual Auto opt-in only, no exchange API or keys.
(() => {
  const el = id => document.getElementById('paper-' + id);
  const fields = () => Array.from(document.querySelectorAll('[data-paper-setting]'));
  let quote = null, busy = false, loaded = false, pending = null, timer = null, lastState = 0, stopped = false, latestAuto = null, latestSettings = null, viewGeneration = 0, pendingView = false;
  const modes = {OFF:'Выключен',ON:'Включён · ждёт закрытую свечу',PAUSED:'На паузе',ERROR:'Ошибка · требуется проверка'};
  const reasons = {
    OFF:'Автоматические входы выключены',AUTO_OFF:'Автоматические входы выключены',NO_SIGNAL:'Подтверждённого сигнала нет',
    STALE_DATA:'Котировки устарели',DUPLICATE_SIGNAL:'Этот сигнал уже обработан',POSITION_ALREADY_OPEN:'Уже есть открытая позиция',
    POSITION_LIMIT:'Достигнут лимит позиций',RISK_LIMIT:'Превышен допустимый риск',POSITION_SIZE_LIMIT:'Превышен допустимый номинал',
    INSUFFICIENT_BALANCE:'Недостаточно свободных виртуальных средств',INVALID_SL:'Некорректный Stop Loss',INVALID_TP:'Некорректный Take Profit',
    INVALID_STOPS:'Некорректная защита или комиссии превышают результат до TP',STOPS_UNAVAILABLE:'Сигнал без SL/TP пропущен',
    SOURCE_MISMATCH:'Источник не совпадает с котировками',TIMEFRAME_MISMATCH:'Не совпадает интервал свечей',MARKET_GAP:'В свечах есть пропуск',
    MARKET_TIMEOUT:'Котировки не ответили вовремя',MARKET_UNAVAILABLE:'Котировки недоступны',SIGNAL_UNAVAILABLE:'Сигнал временно недоступен · ожидается повторная попытка',
    SIGNAL_RETRY_EXHAUSTED:'Три ошибки получения сигнала · требуется ручное возобновление',
    SNAPSHOT_MISMATCH:'История и текущие свечи не совпадают',INVALID_MARKET_DATA:'Некорректные свечи',INVALID_DATA:'Некорректные данные',
    QUOTE_CHANGED:'Подтверждённая цена изменилась',ACTIVATION_BASELINE:'Запомнена исходная свеча; входа нет',
    MISSED_CANDLE_NO_ENTRY:'Пропущенная свеча учтена без входа',RESTART_REQUIRES_RESUME:'После перезапуска нужно ручное возобновление',
    OWNER_NOT_CONFIGURED:'Не настроен доступ владельца',SIGNAL_ERROR:'Ошибка проверки сигнала',ERROR:'Требуется проверка ошибки',
    WAITING_FOR_NEW_CANDLE:'Ожидается новая закрытая свеча',CONFIG_CHANGED:'Настройки изменились',
    AUTO_PREFLIGHT_RISK:'Сохранённый риск должен быть не выше 1%',AUTO_PREFLIGHT_POSITIONS:'Лимит должен быть одна позиция',
    AUTO_PREFLIGHT_STOPS:'Некорректная защита LONG/SHORT',AUTO_PREFLIGHT_POLICY:'Нужно выбрать безопасную политику SL/TP',
    AUTO_PREFLIGHT_VIRTUAL:'Не подтверждён виртуальный режим',INVALID_SETTINGS:'Некорректные настройки риска',
    STARTING_BALANCE_LOCKED:'Начальный баланс нельзя менять после первой сделки',STORAGE_UNAVAILABLE:'Журнал временно недоступен',
    CORRUPT_JOURNAL:'Проверка журнала не пройдена; баланс не сброшен',AUDIT_UNAVAILABLE:'Проверка безопасности недоступна',
    STOP_LOSS:'Достигнут Stop Loss',TAKE_PROFIT:'Достигнут Take Profit',MANUAL:'Ручное действие',
    SKIPPED:'Вход не выполнен',OPENED:'Виртуальная сделка открыта',PAUSED:'Автоматические входы на паузе',
    FRESH:'Свежие данные',CONFIGURATION_CHANGED:'Настройки изменены'
  };
  const signalText = value => ({LONG:'LONG · покупка',SHORT:'SHORT · продажа',WAIT:'Ожидание · входа нет'}[value] || 'Нет подтверждённого сигнала');
  const reasonText = value => !value ? '—' : (reasons[value] || 'Причина не распознана')+' ('+value+')';
  const policyText = value => value === 'SKIP' ? 'SKIP · пропускать сигналы без SL/TP' : value === 'PAPER_SETTINGS' ? 'PAPER_SETTINGS · проценты из настроек Paper' : 'Политика не подтверждена';
  const dateText = value => typeof value === 'number' && Number.isFinite(value) && value > 0 && Number.isFinite(new Date(value).getTime()) ?
    new Date(value).toLocaleString('ru-RU',{timeZone:'UTC'})+' UTC' : 'Нет данных';
  const fieldNames = {starting_balance:'Начальный баланс',commission_pct:'Комиссия',risk_per_trade_pct:'Риск на сделку',maximum_position_size_usdt:'Номинал позиции',maximum_simultaneous_positions:'Лимит позиций',stop_loss_pct:'Stop Loss',take_profit_pct:'Take Profit'};
  const sourceText = value => ({defaults:'Значения по умолчанию','environment variables':'Переменные окружения','supplied configuration':'Переданная конфигурация','persisted configuration':'Сохранённая конфигурация','persisted configuration (original source unknown)':'Сохранённая конфигурация; первоначальный источник неизвестен'}[value] || 'Источник неизвестен');
  let dashboardData = null, dashboardAt = 0, settingsDirty = false, policyDirty = false, activeRequests = new Set();
  function numeric(value) { return (typeof value === 'string' && value.trim() !== '' || typeof value === 'number') && Number.isFinite(Number(value)); }
  function card(container,name,value) {
    const item = document.createElement('div'), label = document.createElement('span'), strong = document.createElement('strong');
    label.textContent = name; strong.textContent = value; item.append(label,strong); container.append(item);
  }
  function unavailableDashboard(note='') {
    el('auto-badge').textContent = 'Нет свежих данных'; el('auto-state').textContent = 'Нет свежих данных';
    el('dashboard-freshness').textContent = 'Нет свежих данных'+(note ? ' · '+note : ' · состояние сервера и котировок не подтверждено');
    el('auto-last').textContent = 'Последняя закрытая свеча: нет свежих данных';
    for (const [id,label] of [['dashboard-signal','Сигнал'],['dashboard-action','Решение'],['dashboard-rejection','Причина']]) el(id).textContent = label+': нет свежих данных';
    el('dashboard-metrics').replaceChildren(); el('auto-position').replaceChildren(); el('auto-position').textContent = 'Нет свежих данных';
    el('auto-history').replaceChildren(); el('auto-history-note').textContent = 'Нет свежих данных';
    el('dashboard-policy').textContent = latestAuto ? 'Последнее подтверждённое состояние: '+latestAuto.status+' · '+latestAuto.symbol+' / '+latestAuto.timeframe+' · '+policyText(latestAuto.fallback_policy)+'. Текущая активность не подтверждена.' : 'Сохранённая политика SL/TP: нет данных.';
    el('auto-start').disabled = true;
  }
  function dashboardFresh() {
    const data=dashboardData, state=data?.auto_paper, selected=scope();
    if (!loaded || stopped || !data || Date.now()-dashboardAt > 30000 || !state || !modes[state.status] ||
        !selected.fresh || selected.symbol !== 'BTCUSDT' || data.statistics_scope !== 'AUTO' ||
        !data.effective_settings || data.effective_settings.account_scope !== 'ALL' || !numeric(data.effective_settings.virtual_balance) || !numeric(data.effective_settings.equity) ||
        !data.statistics || !numeric(data.statistics.net_pnl) || !Number.isInteger(data.statistics.total_trades) || data.statistics.total_trades < 0 ||
        !Array.isArray(data.open_positions) || !Array.isArray(data.closed_trades)) return false;
    if (state.enabled && (selected.timeframe !== state.timeframe || selected.source !== state.source)) return false;
    const steps={'1m':60000,'5m':300000,'15m':900000,'1h':3600000}, last=state.last_processed_candle;
    if (state.status === 'ON' && (!steps[state.timeframe] || !Number.isFinite(last) || last <= 0 || last > Date.now()+1000 || Date.now()-last > 2*steps[state.timeframe])) return false;
    if (data.open_positions.length > 1 || !Number.isInteger(data.statistics.open_positions) || data.statistics.open_positions !== data.open_positions.length) return false;
    return data.open_positions.every(t=>t.entry_type === 'AUTO_SIGNAL' && t.execution_mode === 'PAPER' && t.symbol === 'BTCUSDT' &&
      ['LONG','SHORT'].includes(t.direction) && t.data_status === 'FRESH' && ['entry_price','position_size','stop_loss','take_profit','unrealized_pnl'].every(k=>numeric(t[k])));
  }
  function renderDashboard(data,observedAt=Date.now()) {
    dashboardData=data; dashboardAt=observedAt;
    if (!dashboardFresh()) { unavailableDashboard(); return; }
    const state=data.auto_paper, account=data.effective_settings, stats=data.statistics;
    el('auto-badge').textContent = state.status+' · '+modes[state.status];
    el('auto-state').textContent = state.status+' · '+modes[state.status]+' · '+state.symbol+' / '+state.timeframe;
    el('dashboard-freshness').textContent = 'Состояние получено с сервера. Это виртуальная симуляция, не подтверждение прибыльности.';
    el('auto-last').textContent = 'Последняя обработанная закрытая свеча: '+dateText(state.last_processed_candle);
    const metrics=el('dashboard-metrics'); metrics.replaceChildren();
    for (const [name,value] of [['Виртуальный баланс · весь счёт ALL / USDT',account.virtual_balance],['Средства с учётом позиций · весь счёт ALL / USDT',account.equity],
      ['Реализованный PnL · только AUTO / USDT',stats.net_pnl],['Закрытые сделки · только AUTO',stats.total_trades]]) card(metrics,name,rounded(value));
    el('dashboard-signal').textContent = 'Последний сигнал: '+signalText(state.last_signal);
    const decision=(state.decisions || []).find(row=>row.timestamp === state.last_processed_candle);
    let action=reasonText(state.last_action);
    if (state.last_action === 'OPENED' && decision?.trade_opened !== true) action='Открытие сделки не подтверждено журналом';
    el('dashboard-action').textContent = 'Последнее решение: '+action;
    el('dashboard-rejection').textContent = 'Причина отказа: '+(state.last_rejection_reason ? reasonText(state.last_rejection_reason) : 'Отказ не записан');
    el('dashboard-policy').textContent = 'Сохранённая политика SL/TP: '+policyText(state.fallback_policy)+'. Запуск не изменяет эту политику.';
    el('auto-start').textContent = ['PAUSED','ERROR'].includes(state.status) ? 'Возобновить Авто Paper' : 'Запустить Авто Paper';
    const position=el('auto-position'); position.replaceChildren();position.textContent='';
    if (!data.open_positions.length) position.textContent='Открытых автоматических позиций нет.';
    for (const trade of data.open_positions) {
      card(position,'Направление',signalText(trade.direction));
      for (const [name,value] of [['Цена входа · USDT',trade.entry_price],['Количество · BTC',trade.position_size],['Stop Loss · USDT',trade.stop_loss],['Take Profit · USDT',trade.take_profit],['Нереализованный PnL · AUTO / USDT',trade.unrealized_pnl]]) card(position,name,rounded(value));
    }
    const history=el('auto-history');history.replaceChildren();
    if (data.closed_trades.some(t=>t.entry_type !== 'AUTO_SIGNAL' || t.execution_mode !== 'PAPER')) throw new Error('Неверная атрибуция журнала AUTO.');
    for (const trade of data.closed_trades.slice(0,5)) {
      const item=document.createElement('article'), title=document.createElement('strong'), detail=document.createElement('p');
      title.textContent=signalText(trade.direction)+' · PnL '+rounded(trade.realized_pnl)+' USDT';
      detail.textContent=dateText(trade.exit_time)+' · '+reasonText(trade.exit_reason);item.append(title,detail);history.append(item);
    }
    el('auto-history-note').textContent = stats.total_trades === 0 ? 'Закрытых автоматических сделок пока нет.' :
      'Показано '+Math.min(data.closed_trades.length,5)+' из '+stats.total_trades+' закрытых AUTO-сделок. Полный доступный журнал — в разделе ниже, фильтр AUTO; архив — в резервной копии.';
    draftNotice();
  }
  function draftNotice() {
    const changed=settingsDirty || Boolean(latestSettings && settingsDraftChanged()), policyChanged=policyDirty || Boolean(latestAuto && el('auto-policy').value !== latestAuto.fallback_policy);
    el('dashboard-draft').textContent = changed || policyChanged ? 'Есть несохранённый черновик. Действуют прежние настройки сервера; быстрый запуск заблокирован. Сохраните настройки или явно подтвердите выбранный режим и политику в расширенном разделе.' : '';
  }
  async function loadState() {
    const data=await request(statePath());safety(data);
    if (data.auto_paper) {
      let auto;
      try { auto=(data.statistics_scope || 'ALL') === 'AUTO' ? data : await request('state?scope=AUTO'); }
      catch(error) { data.dashboard_error=error.message || 'Отдельный журнал AUTO не получен.'; return data; }
      safety(auto);
      if (auto.statistics_scope !== 'AUTO') throw new Error('Сервер не подтвердил отдельный журнал AUTO.');
      data.dashboard_view=auto;
    }
    return data;
  }

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
    for (const id of ['refresh','save','quote-refresh','auto-save']) el(id).disabled = busy || Boolean(pending);
    el('save').disabled = busy || Boolean(pending) || !loaded || latestSettings?.editable !== true;
    draftNotice();
    el('auto-start').disabled = busy || Boolean(pending) || !dashboardFresh() || latestAuto?.status === 'ON' || latestAuto?.safety_preflight?.passed !== true || settingsDraftChanged() || policyDirty || settingsDirty || Boolean(latestAuto && el('auto-policy').value !== latestAuto.fallback_policy);
    el('auto-stop').disabled = busy || Boolean(pending) || stopped;
    el('settings-discard').disabled = busy || Boolean(pending) || !latestSettings;
    el('retry').hidden = !pending; el('retry').disabled = busy;
    for (const button of el('positions').querySelectorAll('button')) button.disabled = busy || Boolean(pending);
  }
  function invalidate() { quote = null; if (!dashboardFresh()) unavailableDashboard(); el('quote').textContent = 'Получите новую подтверждённую цену.'; buttons(); }
  async function request(path, body) {
    if (stopped) throw new Error('Страница закрыта; запрос отменён.');
    const controller = new AbortController(); activeRequests.add(controller);
    const timeout = setTimeout(() => controller.abort(), 35000);
    try {
      const options = {credentials:'same-origin', cache:'no-store', signal:controller.signal};
      if (body !== undefined) { options.method = 'POST'; options.headers = {'Content-Type':'application/json','X-Aura-Paper':'local-only'}; options.body = JSON.stringify(body); }
      const response = await fetch('/api/paper/' + path, options);
      el('login').hidden = response.status !== 401;
      if (response.status === 401 || response.status === 403) throw Object.assign(new Error('Виртуальный счёт закрыт. Войдите как aura; пароль — AURA_TESTNET_VIEW_PASSWORD.'),{definitive:true});
      const result = await response.json();
      if (!response.ok) throw Object.assign(new Error((result.code && reasons[result.code] ? reasonText(result.code) : result.message) || 'Запрос виртуальной торговли отклонён.'),{definitive:response.status >= 400 && response.status < 500});
      return result;
    } finally { clearTimeout(timeout); activeRequests.delete(controller); }
  }
  // Number is used only to format server Decimal strings; calculations stay server-side.
  function rounded(value) {
    if (value === null || value === undefined) return '— (нет данных)';
    const number = Number(value);
    if (!Number.isFinite(number)) throw new Error('Некорректное значение действующих настроек.');
    if (number !== 0 && Math.abs(number) < 0.0001) return number.toPrecision(5);
    return number.toLocaleString('ru-RU',{maximumFractionDigits:4});
  }
  function renderSettings(data) {
    latestSettings = null;
    const effective = data.effective_settings, container = el('settings-effective'); container.replaceChildren();
    if (!effective) { el('settings-preflight').textContent = 'Проверка безопасности недоступна; обновите данные перед запуском.'; return; }
    if (effective.account_scope !== 'ALL' || effective.real_money_execution !== 'DISABLED' || effective.exchange_order_placement !== false ||
        typeof effective.editable !== 'boolean' || !effective.values || typeof effective.slippage_supported !== 'boolean') throw new Error('Не подтверждена безопасность действующих настроек.');
    for (const field of fields()) {
      const value = effective.values[field.dataset.paperSetting];
      if (value === null || value === undefined || !Number.isFinite(Number(value)) || String(value) !== String(data.settings[field.dataset.paperSetting]))
        throw new Error('Действующие настройки не совпадают с ответом сервера.');
    }
    const values = effective.values, auto = data.auto_paper;
    const audit = auto && auto.safety_preflight;
    const entries = [['Виртуальный баланс · USDT / ALL',rounded(effective.virtual_balance)],['Средства с учётом позиций · USDT / ALL',rounded(effective.equity)],
      ['Stop Loss по умолчанию · %',rounded(values.stop_loss_pct)],['Take Profit по умолчанию · %',rounded(values.take_profit_pct)],
      ['Комиссия за одну сторону · %',rounded(values.commission_pct)],['Проскальзывание',effective.slippage_supported ? rounded(effective.slippage_pct)+'%' : 'Не поддерживается / не моделируется'],
      ['Максимальный риск на сделку · %',rounded(values.risk_per_trade_pct)],['Максимальный номинал · USDT',rounded(values.maximum_position_size_usdt)],
      ['Максимум открытых позиций',rounded(values.maximum_simultaneous_positions)],['Защитный предел риска Auto · %',rounded(effective.auto_risk_cap_pct)],
      ['Защитный предел позиций Auto',rounded(effective.auto_maximum_open_positions)],['Политика SL/TP',auto ? policyText(auto.fallback_policy) : 'Нет данных'],
      ['Режим Auto / рынок',auto ? auto.status+' · '+auto.symbol+' / '+auto.timeframe : 'Нет данных']];
    for (const [name,value] of entries) {
      const card = document.createElement('div'), label = document.createElement('span'), strong = document.createElement('strong');
      label.textContent = name; strong.textContent = value; card.append(label,strong); container.append(card);
    }
    el('settings-source').textContent = 'Источник настроек: '+sourceText(effective.settings_source)+'. Сохранённые значения важнее переменных окружения; окружение важнее defaults только при создании нового журнала. '+
      Object.entries(effective.initialization_sources || {}).map(([name,source])=>(fieldNames[name] || name)+': '+sourceText(source)).join(' · ')+'. '+
      (effective.editable ? 'Можно редактировать через проверенную форму ниже.' : 'Только просмотр: здесь настройки не редактируются.');
    el('settings-preflight').textContent = !audit ? 'Проверка безопасности недоступна; запуск заблокирован.' :
      (audit.passed ? 'Проверка настроек пройдена. ' : 'Запуск заблокирован: '+(audit.errors || []).map(reasonText).join('; ')+'. ')+
      (auto?.fallback_policy === 'SKIP' ? 'Сигналы без SL/TP пропускаются.' : 'Проценты Paper используются только как явно разрешённая виртуальная защита.')+' Свежесть данных и каждый вход проверяются отдельно сервером.';
    if (audit && typeof audit.passed === 'boolean' && audit.virtual_only === true && audit.exchange_order_placement === false) latestSettings = effective;
  }
  function settingsDraftChanged() {
    return !latestSettings || fields().some(input => String(input.value).trim() !== String(latestSettings.values[input.dataset.paperSetting]));
  }
  function safety(data) {
    if (data.paper !== true || data.real_money_execution !== 'DISABLED' || data.automatic_signal_execution !== false)
      throw new Error('Безопасность виртуального режима не подтверждена. Действия отключены.');
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
    el('curve-note').textContent = `${points.length} / ${data.equity_curve_total} точек · пропуски = нет свежей оценки · просадка по сохранённым оценкам ликвидационного капитала.`;
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
    if (stopped) return;
    safety(data);
    if ((data.statistics_scope || 'ALL') !== (el('scope').value || 'ALL')) throw new Error('Фильтр статистики не совпадает; обновите данные.');
    if (!data.statistics || !Array.isArray(data.open_positions) || !Array.isArray(data.closed_trades) || !Array.isArray(data.equity_curve)) throw new Error('Некорректные данные Paper.');
    loaded = true; lastState = Date.now(); el('data').hidden = false;
    el('storage').textContent = 'Журнал SQLite. На Render без persistent disk он теряется при restart/redeploy. Скачивайте резервные копии; для постоянного хранения настройте PAPER_DB_PATH на диск.';
    const s = data.statistics, metrics = el('metrics'); metrics.replaceChildren();
    for (const [name,value] of [['Баланс выбранного журнала',s.current_balance],['Средства с учётом позиций',s.equity],['Реализованный PnL',s.net_pnl],['Выигрышные сделки · %',s.win_rate],['Фактор прибыли',s.profit_factor],['Максимальная просадка · %',s.maximum_drawdown_pct],['Открытые позиции',s.open_positions],['Закрытые сделки',s.total_trades],['Свободные средства · USDT',s.available_balance],['Доходность · %',s.return_pct],['Сумма положительных исходов',s.gross_profit],['Сумма отрицательных исходов',s.gross_loss],['Средний выигрыш / убыток',`${display(s.average_win)} / ${display(s.average_loss)}`],['Плановое прибыль / риск',s.risk_reward],['Серия выигрышей / убытков',`${s.consecutive_wins} / ${s.consecutive_losses}`],['Комиссии · USDT',s.total_commissions]]) {
      const card = document.createElement('div'), label = document.createElement('span'), valueNode = document.createElement('strong');
      label.textContent = name; valueNode.textContent = display(value); card.append(label,valueNode); metrics.append(card);
    }
    for (const input of fields()) if (!settingsDirty && document.activeElement !== input) {
      input.value = (data.dashboard_view || data).settings[input.dataset.paperSetting];
      input.disabled = data.effective_settings?.editable === false || input.dataset.paperSetting === 'starting_balance' && (data.starting_balance_locked === true || s.total_trades+s.open_positions > 0);
    }
    el('positions').replaceChildren();
    for (const trade of data.open_positions) {
      const row = cells(el('positions'),[trade.symbol+' / '+trade.direction,trade.entry_price,trade.position_size,trade.stop_loss,trade.take_profit,trade.unrealized_pnl,trade.data_status]);
      const cell = document.createElement('td'), button = document.createElement('button'); button.textContent = 'Закрыть виртуальную позицию';
      button.addEventListener('click',() => close(trade)); cell.append(button); row.append(cell);
    }
    if (!data.open_positions.length) cells(el('positions'),['Нет открытых виртуальных позиций']);
    el('trades').replaceChildren();
    for (const t of data.closed_trades) cells(el('trades'),[new Date(t.exit_time).toISOString(),t.symbol+' / '+t.direction,t.entry_price,t.exit_price,t.position_size,t.commissions,t.realized_pnl,t.pnl_pct,t.entry_reason,t.exit_reason,t.source+' / '+t.timeframe,t.entry_type === 'AUTO_SIGNAL' ? 'Автоматическая' : 'Ручная']);
    if (!data.closed_trades.length) cells(el('trades'),['Нет закрытых виртуальных сделок']);
    el('journal-note').textContent = `Показано ${data.closed_trades.length} из ${data.closed_trades_total}; полный архив — резервная копия SQLite. Суммы выигрышей/убытков учитывают комиссии. Profit Factor без убытков = —.`;
    renderAuto(data.dashboard_view || data); renderSettings(data.dashboard_view || data); renderDashboard(data.dashboard_view || null); if(data.dashboard_error)unavailableDashboard(data.dashboard_error); renderCurve(data); buttons();
  }
  function statePath() {
    const mode = el('scope').value || 'ALL';
    return 'state' + (mode === 'ALL' ? '' : '?scope=' + encodeURIComponent(mode));
  }
  function renderAuto(data) {
    const state = data.auto_paper;
    if (!state) { latestAuto=null; return; } // Нет подтверждённого сервером режима.
    if (!['OFF','ON','PAUSED','ERROR'].includes(state.status) || typeof state.enabled !== 'boolean' || state.symbol !== 'BTCUSDT' || !['1m','5m','15m','1h'].includes(state.timeframe) || !['SKIP','PAPER_SETTINGS'].includes(state.fallback_policy) || typeof state.source !== 'string' || !state.source || (state.status === 'OFF') !== !state.enabled) throw new Error('Некорректный Auto Paper state');
    latestAuto = state;
    // Основной статус выводится только после проверки свежести панели.

    for (const [id,value] of [['auto-mode',state.enabled ? 'ON' : 'OFF'],['auto-policy',state.fallback_policy]])
      if (document.activeElement !== el(id) && !policyDirty) el(id).value = value;
    el('auto-metrics').replaceChildren();
    const stats = data.auto_statistics || {};
    for (const [name,value] of [['Закрытые сделки AUTO',stats.total_trades],['PnL только AUTO',stats.net_pnl],['Доля выигрышных AUTO · %',stats.win_rate],['Фактор прибыли только AUTO',stats.profit_factor]]) {
      const card = document.createElement('div'), label = document.createElement('span'), strong = document.createElement('strong');
      label.textContent = name; strong.textContent = display(value); card.append(label,strong); el('auto-metrics').append(card);
    }
    el('auto-decisions').replaceChildren();
    for (const row of state.decisions || []) cells(el('auto-decisions'),[new Date(row.timestamp).toISOString(),row.symbol+' / '+row.timeframe,
      signalText(row.signal_result),row.auto_status,row.trade_opened ? 'Да' : 'Нет',reasonText(row.rejection_reason || row.action)]);
  }
  async function applyAuto(enabled,policy,quick=false) {
    if (stopped || busy || pending) return;
    const selected=scope();
    if (enabled && (!loaded || !latestSettings || settingsDraftChanged() || settingsDirty)) { status('Сохраните или отмените черновик настроек перед запуском.'); return; }
    if (enabled && !dashboardFresh()) { status('Нет свежих данных AUTO. Обновите состояние перед запуском.'); return; }
    if (enabled && latestAuto?.safety_preflight?.passed !== true) { status('Запуск заблокирован: '+(latestAuto?.safety_preflight?.errors || ['AUDIT_UNAVAILABLE']).map(reasonText).join('; ')); return; }
    if (enabled && (!selected.fresh || selected.symbol !== 'BTCUSDT')) { status('Для запуска нужен свежий график BTCUSDT. Нет свежих данных.'); return; }
    if (enabled && quick && (!dashboardFresh() || policyDirty || !latestAuto || policy !== latestAuto.fallback_policy || el('auto-policy').value !== latestAuto.fallback_policy)) { status('Есть несохранённый черновик политики или нет свежих данных. Подтвердите изменения в расширенном разделе.'); return; }
    if (enabled && quick && ['PAUSED','ERROR'].includes(latestAuto.status) && (selected.timeframe !== latestAuto.timeframe || selected.source !== latestAuto.source)) { status('Для возобновления выберите свежий график сохранённого интервала и источника.'); return; }
    if (enabled && !['SKIP','PAPER_SETTINGS'].includes(policy)) { status('Политика SL/TP не подтверждена.'); return; }
    if (enabled && !window.confirm('Включить только виртуальную торговлю BTCUSDT / '+selected.timeframe+'?\nПолитика: '+policyText(policy)+'\nРеальные деньги не используются. Сервер проверит безопасность.')) return;
    if (enabled) {
      const after=scope();
      if (!after.fresh || after.symbol !== selected.symbol || after.timeframe !== selected.timeframe || after.source !== selected.source || Date.now()-lastState > 30000) { status('Нет свежих данных или график изменился во время подтверждения. Обновите состояние.'); return; }
    }
    const body=enabled ? {enabled:true,symbol:'BTCUSDT',timeframe:selected.timeframe,expected_source:selected.source,fallback_policy:policy} : {enabled:false};
    busy=true;unavailableDashboard('запрос изменения режима ещё не подтверждён');buttons();
    try {
      const acknowledgement=await request('auto',body);
      if (acknowledgement.enabled !== enabled || acknowledgement.status !== (enabled ? 'ON' : 'OFF') || enabled && (acknowledgement.fallback_policy !== policy || acknowledgement.symbol !== selected.symbol || acknowledgement.timeframe !== selected.timeframe || acknowledgement.source !== selected.source)) throw new Error('Сервер не подтвердил выбранный режим.');
      policyDirty=false;
      render(await loadState());invalidate();
      status(enabled ? 'Состояние перечитано с сервера. Вход не гарантирован; решения принимаются по закрытым свечам.' : latestAuto?.status === 'OFF' && latestAuto?.enabled === false ? 'Команда OFF подтверждена сервером. Новые Auto-входы выключены; защита открытых позиций зависит от свежих данных.' : 'Последнее состояние не подтверждает OFF. Проверьте сервер и повторите остановку явно.');
    } catch(error) { fail(error);status((error.message || 'Сервер не ответил.')+' Результат смены режима не подтверждён. Обновите состояние; не считайте запуск или остановку выполненными.'); }
    finally { busy=false;buttons();if(pendingView){pendingView=false;refresh();} }
  }
  function saveAuto() { return applyAuto(el('auto-mode').value === 'ON',el('auto-policy').value); }
  function fail(error) { latestSettings = null; unavailableDashboard('сервер недоступен или снимок устарел'); status(error.message || 'Виртуальный счёт временно недоступен.'); loaded = false; el('data').hidden = true; invalidate(); }
  async function refresh() {
    if (stopped || busy || pending) return;
    busy = true; buttons();
    const generation = viewGeneration;
    try {
      const data = await loadState();
      if (generation !== viewGeneration) return;
      render(data); status(data.dashboard_error ? 'Нет свежих данных AUTO. '+data.dashboard_error+' Ручной журнал получен отдельно.' : 'Данные получены с сервера. Только виртуальные средства; состояние Auto показано отдельно.');
    }
    catch(error) { fail(error); }
    finally { busy = false; buttons(); if (pendingView) { pendingView = false; refresh(); } }
  }
  async function getQuote() {
    if (stopped || busy || pending) return;
    const before = scope();
    if (!before.fresh || before.symbol !== 'BTCUSDT' || !before.source) { status('Нужен свежий график BTCUSDT.'); invalidate(); return; }
    busy = true; buttons();
    try {
      const result = await request('quote?symbol=BTCUSDT&timeframe='+encodeURIComponent(before.timeframe)); safety(result);
      const after = scope();
      if (!after.fresh || after.symbol !== before.symbol || after.timeframe !== before.timeframe || result.source !== after.source) throw new Error('График изменился или источник не совпадает.');
      quote = result; el('quote').textContent = `${result.price} USDT · ${result.source} · ${result.timeframe} · закрытие ${dateText(result.price_time)}`;
      status('Цена подтверждена. Виртуальное исполнение по закрытию проверенной свечи.');
    } catch(error) { invalidate(); status(error.message); }
    finally { busy = false; buttons(); if (pendingView) { pendingView = false; refresh(); } }
  }
  async function execute() {
    if (stopped || !pending || busy) return;
    busy = true; unavailableDashboard('ручное действие ещё не подтверждено'); buttons();
    try { await request(pending.path,pending.body); pending = null; invalidate(); render(await loadState()); status('Виртуальное действие выполнено. Биржевые ордера не отправлялись.'); }
    catch(error) {
      if (error.definitive) { pending = null; invalidate(); }
      status(error.message + (pending ? ' Исход неизвестен: повторите с тем же request ID; не открывайте новую сделку.' : ''));
    } finally { retainPending(); busy = false; buttons(); }
  }
  function open() {
    if (stopped || !matched() || pending) return;
    const reason = el('reason').value.trim(); if (!reason) { status('Укажите причину входа.'); return; }
    pending = {path:'positions/open',body:{request_id:crypto.randomUUID(),symbol:quote.symbol,timeframe:quote.timeframe,direction:el('direction').value,
      expected_source:quote.source,expected_candle_time:quote.candle_time,expected_price:quote.price,entry_reason:reason,
      position_size:el('size').value.trim() || null,stop_loss:el('stop').value.trim() || null,take_profit:el('target').value.trim() || null,signal_id:null}};
    retainPending(); execute();
  }
  function close(trade) {
    if (stopped || busy || pending) return;
    pending = {path:'positions/'+encodeURIComponent(trade.id)+'/close',body:{request_id:crypto.randomUUID(),exit_reason:'Ручное закрытие владельцем'}};
    retainPending(); execute();
  }
  async function save() {
    if (stopped || busy || pending || !loaded || latestSettings?.editable !== true) return;
    const values = Object.fromEntries(fields().map(i => [i.dataset.paperSetting,i.dataset.paperSetting === 'maximum_simultaneous_positions' ? Number(i.value) : i.value.trim()]));
    busy = true; buttons();
    try { await request('settings',values); settingsDirty=false; render(await loadState()); status('Настройки сохранены. Открытые позиции не изменены.'); invalidate(); }
    catch(error) { status(error.message); }
    finally { busy = false; buttons(); if (pendingView) { pendingView = false; refresh(); } }
  }
  el('settings-discard').addEventListener('click',()=>{
    if (stopped || busy || pending || !latestSettings) return;
    settingsDirty=false;policyDirty=false;
    for(const input of fields())input.value=latestSettings.values[input.dataset.paperSetting];
    if(latestAuto){el('auto-policy').value=latestAuto.fallback_policy;el('auto-mode').value=latestAuto.enabled ? 'ON' : 'OFF';}
    buttons();status('Черновик отменён. Восстановлены последние полученные настройки сервера; запросы изменения не отправлялись.');
  });
  el('auto-save').addEventListener('click',saveAuto);
  el('auto-start').addEventListener('click',()=>applyAuto(true,latestAuto?.fallback_policy,true));
  el('auto-stop').addEventListener('click',()=>applyAuto(false,latestAuto?.fallback_policy,true));
  for (const input of fields()) input.addEventListener('input',()=>{settingsDirty=true;buttons();});
  for (const id of ['auto-policy','auto-mode']) el(id).addEventListener('change',()=>{policyDirty=true;buttons();});
  el('scope').addEventListener('change',() => { viewGeneration++; loaded = false; el('data').hidden = true; invalidate(); if (busy) pendingView = true; else refresh(); });
  el('refresh').addEventListener('click',refresh); el('quote-refresh').addEventListener('click',getQuote);
  el('open').addEventListener('click',open); el('save').addEventListener('click',save); el('retry').addEventListener('click',execute);
  document.getElementById('symbol').addEventListener('change',invalidate);
  document.getElementById('timeframes').addEventListener('click',invalidate);
  document.addEventListener('market-unavailable',invalidate);
  document.addEventListener('market-data-changed',()=>{if(!dashboardFresh())unavailableDashboard();else if(dashboardData)renderDashboard(dashboardData,dashboardAt);buttons();});
  function expire() {
    if (loaded && Date.now()-lastState > 30000) fail(new Error('Нет свежих данных. Снимок виртуального счёта устарел.' + (pending ? ' Повторите неподтверждённое действие с прежним ID.' : '')));
  }
  timer = setInterval(() => { expire(); buttons(); if (!document.hidden) refresh(); },15000);
  document.addEventListener('visibilitychange',() => { expire(); if (!document.hidden) refresh(); });
  window.addEventListener('pagehide',() => { stopped = true; for(const controller of activeRequests)controller.abort(); unavailableDashboard('страница закрыта'); clearInterval(timer); loaded = false; el('data').hidden = true; invalidate(); });
  window.addEventListener('pageshow',() => { if (stopped) location.reload(); });
  if (pending) { status('Есть неподтверждённое paper действие. Повторите его с прежним request ID.'); buttons(); }
  else refresh();
})();

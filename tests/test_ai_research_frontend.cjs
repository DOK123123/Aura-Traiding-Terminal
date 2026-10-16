// Offline behavioral checks: no LLM, HTTP, account, scheduler or execution access.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/research.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '../static/research.html'), 'utf8');

function environment(answer) {
  const elements = new Map(), nodes = [], requests = [], timers = new Map();
  let nextTimer = 0, innerHTMLWrites = 0;
  class Element {
    constructor(tag = '') {
      this.tag = tag; this.children = []; this.events = {}; this.textContent = '';
      this.hidden = false; this.disabled = false; this.value = ''; nodes.push(this);
    }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = [...children]; }
    addEventListener(name, fn) { this.events[name] = fn; }
    set innerHTML(_) { innerHTMLWrites++; throw new Error('Unsafe HTML insertion'); }
  }
  for (const match of html.matchAll(/<(\w+)\b[^>]*\bid="(research-[^"]+)"[^>]*>/g)) {
    const node = new Element(match[1]); node.id = match[2];
    node.disabled = /\bdisabled\b/.test(match[0]); node.hidden = /\bhidden\b/.test(match[0]);
    elements.set(node.id, node);
  }
  const el = id => { assert.ok(elements.has('research-' + id), 'HTML element ' + id); return elements.get('research-' + id); };
  el('hypothesis').value = 'MEAN_REVERSION';
  const sandbox = {
    document: {
      getElementById: id => elements.get(id),
      createElement: tag => new Element(tag),
      createTextNode: value => Object.assign(new Element('#text'), {textContent: value}),
      querySelectorAll: tag => nodes.filter(node => node.tag === tag),
    },
    AbortController, Date,
    setTimeout: fn => { const id = ++nextTimer; timers.set(id, fn); return id; },
    clearTimeout: id => timers.delete(id),
    setInterval() { throw new Error('Autonomous research polling prohibited'); },
    fetch: async (url, options) => {
      requests.push({url, options});
      const response = await (typeof answer === 'function' ? answer(url, options) : answer);
      if (response instanceof Error) throw response;
      const status = response.status || 200;
      return {status, ok: status < 400, json: async () => response.body || response};
    },
  };
  vm.createContext(sandbox); vm.runInContext(source, sandbox);
  const flush = async () => { for (let i = 0; i < 60; i++) await Promise.resolve(); };
  return {
    el, nodes, requests, timers, flush,
    setResponse: value => { answer = value; },
    click: async node => { if (typeof node === 'string') node = el(node); if (!node.disabled) node.events.click(); await flush(); },
    innerHTMLWrites: () => innerHTMLWrites,
  };
}
function state(overrides = {}) {
  return {
    research_only: true, activation_available: false, manual_only: true,
    llm: {enabled: false, status: 'AI_NOT_CONFIGURED'},
    agents: ['RESEARCHER', 'BACKTESTER', 'AUDITOR'].map(id => ({id, state: 'IDLE', capabilities: ['research only']})),
    dataset: {source: 'Binance Spot public archive', total_candles: 960, start: 1700000000, end_exclusive: 1700086400, sha256: 'fixture-hash'},
    registry: {MEAN_REVERSION: {title: 'Mean Reversion', rationale: 'Unverified hypothesis.', rules: 'Closed candles only.'}},
    sources: {SOURCE: {title: 'Verified source', year: 2021, url: 'https://doi.org/10.1093/rfs/hhaa113', scope: 'No current profitability claim.'}},
    queue: [], llm_calls: [], ...overrides,
  };
}
function experiment(overrides = {}) {
  return {
    id: 'experiment/with space', state: 'NEEDS_VALIDATION', report: {
      research_only: true, activation_available: false, final_test_is_independent: false,
      config_hash: 'frozen-hash', auditor: {status: 'NEEDS_VALIDATION', reasons: ['Reused exploratory test.']},
      runs: [{split: 'test', scale: '1.0', metrics: {trades: 0, net_profit: '0', return_pct: '0', profit_factor: null, win_rate: null, expectancy: null, max_drawdown_pct: '0', sharpe: null, fees: '0'}}],
      audits: [{split: 'test', scale: '1.0', status: 'PASS', closed_trades_checked: 0, independent_math: 'PASS'}], ...overrides,
    },
  };
}
function assertResearchRequests(e) {
  for (const {url, options} of e.requests) {
    assert.match(url, /^\/api\/research(?:\/|$)/);
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.cache, 'no-store');
    if (options.method === 'POST') {
      assert.equal(options.headers['X-Aura-Lab'], 'research-only');
      assert.equal(options.headers['Content-Type'], 'application/json');
    }
  }
}

test('Research startup performs no fetch, timer, queued job or LLM call', async () => {
  const e = environment(state()); await e.flush();
  assert.equal(e.requests.length, 0); assert.equal(e.timers.size, 0);
  assert.equal(e.el('idea').disabled, true); assert.equal(e.el('result').hidden, true);
});
test('owner manually refreshes status without starting queued work or LLM', async () => {
  const e = environment(state({queue: [{id: 'queued', hypothesis: 'MEAN_REVERSION', state: 'QUEUED'}]}));
  await e.click('refresh'); assert.equal(e.requests.length, 1);
  assert.equal(e.requests[0].url, '/api/research'); assert.equal(e.requests[0].options.method, undefined);
  assert.equal(e.el('agents').children.length, 3); assert.match(e.el('ai').textContent, /AI_NOT_CONFIGURED/);
  assert.equal(e.el('idea').disabled, true); assert.equal(e.timers.size, 0); assertResearchRequests(e);
});
test('enqueue is an explicit protected POST and does not execute the experiment', async () => {
  const e = environment((url) => url === '/api/research/queue' ? {id: 'fixed-config'} : state());
  e.el('hypothesis').value = 'LIQUIDITY_SWEEP'; await e.click('enqueue');
  assert.deepEqual(e.requests.map(r => r.url), ['/api/research/queue', '/api/research']);
  assert.equal(e.requests[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(e.requests[0].options.body), {hypothesis: 'LIQUIDITY_SWEEP'});
  assert.match(e.el('status').textContent, /fixed-config/); assertResearchRequests(e);
});
test('queued run requires a separate click and encodes the experiment ID', async () => {
  const e = environment(state({queue: [{id: 'queued/id with space', hypothesis: 'MEAN_REVERSION', state: 'QUEUED'}]}));
  await e.click('refresh');
  e.setResponse(url => url.endsWith('/run') ? experiment() : state());
  await e.click(e.el('queue').children[0].children.at(-1).children[0]);
  assert.equal(e.requests[1].url, '/api/research/queue/queued%2Fid%20with%20space/run');
  assert.equal(e.requests[1].options.method, 'POST'); assert.equal(e.requests[1].options.body, '{}');
  assert.equal(e.el('result').hidden, false); assert.match(e.el('audit').textContent, /NEEDS_VALIDATION/);
  assert.equal(e.el('export').href, '/api/research/experiments/experiment%2Fwith%20space/export');
  assert.equal(e.el('metrics').children[0].children[3].textContent, '0');
  assert.equal(e.el('metrics').children[0].children[5].textContent, '—'); assertResearchRequests(e);
});
test('saved experiment is read with GET and never rerun automatically', async () => {
  const e = environment(state({queue: [{id: 'saved', hypothesis: 'MEAN_REVERSION', state: 'NEEDS_VALIDATION'}]}));
  await e.click('refresh'); e.setResponse(url => url.endsWith('/saved') ? experiment() : state());
  await e.click(e.el('queue').children[0].children.at(-1).children[0]);
  assert.equal(e.requests[1].url, '/api/research/experiments/saved');
  assert.equal(e.requests[1].options.method, undefined); assertResearchRequests(e);
});
test('LLM remains disabled without configuration; configured call is explicit advisory-only', async () => {
  const e = environment(state()); await e.click('idea'); assert.equal(e.requests.length, 0);
  e.setResponse(state({llm: {enabled: true, status: 'READY'}})); await e.click('refresh');
  assert.equal(e.el('idea').disabled, false); assert.equal(e.requests.length, 1);
  e.setResponse(url => url.endsWith('/ideas') ? {proposal: '<img src=x onerror=alert(1)>'} : state({llm: {enabled: true, status: 'READY'}}));
  await e.click('idea'); assert.equal(e.requests[1].url, '/api/research/ideas');
  assert.equal(e.requests[1].options.method, 'POST');
  assert.match(e.el('proposal').textContent, /<img/); assert.match(e.el('status').textContent, /ADVISORY_ONLY_UNVERIFIED/);
  assert.equal(e.innerHTMLWrites(), 0); assertResearchRequests(e);
});
test('interrupted work recovery is manual, protected and never starts a retry', async () => {
  const e = environment(url => url.endsWith('/recover-interrupted') ? {interrupted: 2} : state());
  await e.click('recover'); assert.deepEqual(e.requests.map(r => r.url), ['/api/research/recover-interrupted', '/api/research']);
  assert.equal(e.requests[0].options.method, 'POST'); assert.match(e.el('status').textContent, /2/);
  assertResearchRequests(e);
});
test('401 and 403 show owner authentication error without fabricated results', async () => {
  for (const status of [401, 403]) {
    const e = environment({status}); await e.click('refresh');
    assert.match(e.el('status').textContent, /Требуется вход владельца/);
    assert.equal(e.el('result').hidden, true); assert.equal(e.el('idea').disabled, true);
    assert.equal(e.el('refresh').disabled, false); assert.equal(e.requests.length, 1);
  }
  assert.match(html, /href="\/api\/research\/login"/);
});
test('untrusted server text uses textContent and source links allow only DOI HTTPS', async () => {
  const payload = '<svg onload=alert(1)>', e = environment(state({
    agents: [{id: payload, state: payload, capabilities: [payload]}],
    registry: {X: {title: payload, rationale: payload, rules: payload}},
    sources: {X: {title: payload, year: 2026, url: 'javascript:alert(1)', scope: payload}},
    llm_calls: [{error: payload}],
  }));
  await e.click('refresh');
  assert.match(e.el('agents').children[0].children[0].textContent, /<svg/);
  assert.equal(e.el('registry').children[0].children[0].textContent, payload);
  assert.equal(e.el('sources').children[0].children[0].href, undefined);
  assert.match(e.el('calls').textContent, /<svg/); assert.equal(e.innerHTMLWrites(), 0);
  e.setResponse(state()); await e.click('refresh');
  assert.equal(e.el('sources').children[0].children[0].href, 'https://doi.org/10.1093/rfs/hhaa113');
});
test('unsafe research identity or production activation claims are rejected', async () => {
  for (const patch of [{research_only: false}, {activation_available: true}, {manual_only: false}]) {
    const e = environment(state(patch)); await e.click('refresh');
    assert.match(e.el('status').textContent, /Invalid research identity/); assert.equal(e.el('agents').children.length, 0);
  }
  const e = environment(state({queue: [{id: 'bad', state: 'DONE', hypothesis: 'MEAN_REVERSION'}]}));
  await e.click('refresh'); e.setResponse(experiment({activation_available: true}));
  await e.click(e.el('queue').children[0].children.at(-1).children[0]);
  assert.match(e.el('status').textContent, /Invalid research boundary/);
  assert.equal(e.el('metrics').children.length, 0);
});
test('pending request disables controls and suppresses duplicate execution taps', async () => {
  let release; const e = environment(new Promise(resolve => { release = resolve; }));
  e.el('enqueue').events.click(); e.el('enqueue').events.click(); await e.flush();
  assert.equal(e.requests.length, 1); assert.equal(e.el('refresh').disabled, true);
  e.setResponse(state()); release({id: 'one'}); await e.flush();
  assert.equal(e.el('enqueue').disabled, false); assert.equal(e.requests.length, 2); assertResearchRequests(e);
});
test('backend and aborted requests show errors without automatic retry or execution requests', async () => {
  const e = environment({status: 422, body: {code: '<script>bad</script>'}}); await e.click('enqueue');
  assert.equal(e.el('status').textContent, '<script>bad</script>'); assert.equal(e.requests.length, 1);
  const abort = Object.assign(new Error('aborted'), {name: 'AbortError'});
  e.setResponse(abort); await e.click('refresh'); assert.match(e.el('status').textContent, /Ответ потерян/);
  assert.equal(e.requests.length, 2); assert.equal(e.timers.size, 0); assert.equal(e.innerHTMLWrites(), 0);
  assertResearchRequests(e);
});

/* Aura 5.0 isolated preview: presentation only. No POST, order or account access. */
(function (root) {
  'use strict';
  const SOURCE = 'BITGET_BTCUSDT_USDT_FUTURES_PUBLIC_V2';
  const TABS = ['home', 'signals', 'chart', 'more'];
  const LABELS = {home:'Главная', signals:'Сигналы', chart:'График', more:'Ещё'};

  function resolveTab(hash) {
    const match = /^#app-(home|signals|chart|more)$/.exec(String(hash || ''));
    return match ? match[1] : 'home';
  }

  // Fail closed: archived candles, historical prices, offline snapshots and a
  // server's unsupported LIVE label must never be shown as current Bid/Ask.
  function homeState(data, now, threshold, usable) {
    const noQuote = {state:'STALE', reason:'Нет подтверждённых свежих Bid/Ask Bitget', quote:null, candidate:null};
    if (!data || data.scope !== 'AURA6_PUBLIC_OBSERVER_ONLY' ||
        data.execution_enabled !== false || data.account_connected !== false ||
        data.observer?.running !== true || !Number.isFinite(data.server_time) ||
        Math.abs(now - data.server_time) > 10 || !Array.isArray(data.fresh_frames)) return noQuote;
    const quotes = data.quotes || {};
    let quote = null, frame = '';
    for (const tf of ['5m', '15m', '1h', '4h']) {
      const q = quotes[tf];
      if (!data.fresh_frames.includes(tf) || q?.source !== SOURCE ||
          ![q.bid,q.ask,q.time,q.received_at].every(Number.isFinite) ||
          q.bid <= 0 || q.ask < q.bid || (q.ask-q.bid)/q.bid > .002 ||
          now < q.time || now-q.time > 5 || now < q.received_at || now-q.received_at > 5) continue;
      if (!quote || q.received_at > quote.received_at) {quote=q;frame=tf;}
    }
    if (!quote) return noQuote;
    const validThreshold = Number.isInteger(threshold) && threshold >= 50 && threshold <= 100 ? threshold : 50;
    const valid = Array.isArray(data.confidence_candidates) && typeof usable === 'function'
      ? data.confidence_candidates.filter(c => usable(data,c,now,validThreshold)) : [];
    valid.sort((a,b) => b.score-a.score || a.direction.localeCompare(b.direction));
    return {state:valid.length?'WATCH':'WAIT',reason:valid.length
      ? 'Непроверенная исследовательская гипотеза · не сигнал к исполнению'
      : 'Нет свежих исследовательских LONG/SHORT выше порога',
      quote,frame,candidate:valid[0] || null,threshold:validThreshold};
  }

  root.AuraMobileShell={resolveTab,homeState};
  if (typeof module !== 'undefined') module.exports={resolveTab,homeState};
  if (!root.document || document.body?.dataset.manualPreview !== 'true' ||
      !document.getElementById('aura-confidence')) return;

  function build() {
    const main=document.querySelector('main');
    if (!main || main.querySelector('#aura-app')) return;
    document.body.dataset.auraApp='mobile';
    const el=(tag,className,textValue) => {
      const node=document.createElement(tag);
      if(className) node.className=className;
      if(textValue!=null) node.textContent=textValue;
      return node;
    };
    const shell=el('div','aura-app');shell.id='aura-app';
    const panes={};
    for(const key of TABS){
      const pane=el('section','aura-tab-pane');pane.id='app-'+key;
      pane.setAttribute('role','tabpanel');pane.setAttribute('aria-label',LABELS[key]);
      pane.setAttribute('aria-labelledby','app-tab-'+key);
      panes[key]=pane;shell.append(pane);
    }
    main.prepend(shell);
    const move=(selector,target) => {const node=document.querySelector(selector);if(node)target.append(node);return node;};
    const heading=el('div','aura-screen-title');heading.append(el('p','aura-overline','AURA · MANUAL TRADER 5.0'));
    heading.append(el('h1','', 'Главная'));panes.home.append(heading);
    const warning=move('body > .analyst-warning',panes.home);
    if(warning)warning.classList.add('aura-legal-warning');
    const hero=el('section','aura-home-card');hero.setAttribute('aria-label','Обзор Bitget BTCUSDT');
    hero.append(el('p','aura-overline','BITGET · BTCUSDT · USDT-M FUTURES'));
    const row=el('div','aura-home-row');
    const title=el('h2','', 'Обзор рынка');
    const badge=el('span','aura-live-badge','ПРОВЕРЯЕМ');badge.id='app-market-state';badge.setAttribute('role','status');
    row.append(title,badge);hero.append(row);
    const quote=el('div','aura-home-quote','—');quote.id='app-bid-ask';hero.append(quote);
    const updated=el('p','aura-subtle','Ожидание подтверждения источника…');updated.id='app-quote-time';hero.append(updated);
    const state=el('section','aura-home-signal');state.setAttribute('aria-label','Текущая исследовательская оценка');
    const stateHeading=el('h2','', 'Сейчас');state.append(stateHeading);
    const signal=el('p','aura-signal-head','WAIT');signal.id='app-signal-state';signal.setAttribute('role','status');
    const details=el('p','aura-subtle','Исследовательский сигнал не подтверждён');details.id='app-signal-detail';
    state.append(signal,details);hero.append(state);
    const actions=el('div','aura-quick-actions');
    const go=(label,target) => {const b=el('button','aura-action',label);b.type='button';b.addEventListener('click',()=>activate(target,true));return b;};
    actions.append(go('Смотреть сигналы','signals'),go('Открыть график','chart'));
    hero.append(actions);panes.home.append(hero);
    const tip=el('p','aura-home-note','Балл Signal Confidence — согласованность технических признаков, а не вероятность прибыли. Даже WATCH не даёт разрешения на сделку. CONFIRMED без доказанного преимущества запрещён.');
    panes.home.append(tip);
    const journalAction=go('Мой журнал и настройки','more');journalAction.classList.add('aura-journal-shortcut');panes.home.append(journalAction);

    const signalsHeading=el('div','aura-screen-title');signalsHeading.append(el('p','aura-overline','ИССЛЕДОВАНИЕ · НЕ КОМАНДА НА ВХОД'));
    signalsHeading.append(el('h1','','Сигналы'));panes.signals.append(signalsHeading);
    move('#aura-confidence',panes.signals);
    const advancedSignals=el('details','aura-advanced');advancedSignals.append(el('summary','', 'Дополнительные сценарии и диагностика WATCH'));
    move('#aura-signal-center',advancedSignals);
    move('#aura-live-analyst',advancedSignals);
    move('#aura-analyst',advancedSignals);
    move('nav[aria-label="Аналитический помощник"]',advancedSignals);
    panes.signals.append(advancedSignals);

    const chartHeading=el('div','aura-screen-title');chartHeading.append(el('p','aura-overline','СВЕЧИ · РУЧНАЯ РАЗМЕТКА'));
    chartHeading.append(el('h1','','График'));panes.chart.append(chartHeading);
    for(const selector of ['.toolbar','#status','.feed-strip','#live-candle','.terminal-grid'])move(selector,panes.chart);

    const moreHeading=el('div','aura-screen-title');moreHeading.append(el('p','aura-overline','ЖУРНАЛ · НАСТРОЙКИ · ДИАГНОСТИКА'));
    moreHeading.append(el('h1','','Ещё'));panes.more.append(moreHeading);
    const journal=el('section','aura-more-card');journal.append(el('h2','','Журнал сигналов'));
    journal.append(el('p','aura-subtle','Локальная история Signal Confidence в этом браузере. Не является историей исполненных сделок.'));
    const sourceJournal=document.querySelector('#aura-confidence details');
    if(sourceJournal)journal.append(sourceJournal);
    panes.more.append(journal);
    const settings=el('section','aura-more-card');settings.append(el('h2','','Оформление'));
    const themeLabel=el('label','aura-theme-label','Тема интерфейса');
    const theme=el('select','');theme.id='app-theme';
    for(const [key,label] of [['system','Как в устройстве'],['dark','Тёмная'],['light','Светлая']]){
      const opt=el('option','',label);opt.value=key;theme.append(opt);
    }
    const key='aura5.ui.theme';
    const getTheme=()=>{try{return localStorage.getItem(key)||'system';}catch{return 'system';}};
    const setTheme=value=>{
      const safe=['system','dark','light'].includes(value)?value:'system';
      if(safe==='system')delete document.body.dataset.auraTheme;
      else document.body.dataset.auraTheme=safe;
      try{localStorage.setItem(key,safe);}catch{}
      theme.value=safe;
    };
    setTheme(getTheme());theme.addEventListener('change',()=>setTheme(theme.value));
    themeLabel.append(theme);settings.append(themeLabel);
    panes.more.append(settings);
    const virtual=el('section','aura-more-card');virtual.append(el('h2','','Ручной виртуальный счёт'));
    virtual.append(el('p','aura-subtle','Учебная панель отдельно от реального Bitget и Bybit Demo. Открытие позиции требует отдельного подтверждения; интерфейс сам ничего не открывает.'));
    move('#manual-paper-panel',virtual);panes.more.append(virtual);
    const diag=el('details','aura-advanced');diag.append(el('summary','','Диагностика и инструменты анализа'));
    move('#aura-replay-panel',diag);
    const previewButton=document.getElementById('preview-check');if(previewButton)diag.append(previewButton.closest('section.panel'));
    move('.page-heading',diag);move('footer',diag);panes.more.append(diag);

    const nav=el('nav','aura-bottom-nav');nav.setAttribute('aria-label','Разделы приложения');nav.setAttribute('role','tablist');
    const buttons={},icons={home:'⌂',signals:'↗',chart:'▥',more:'☷'};
    for(const key of TABS){const b=el('button','aura-nav-button');b.type='button';b.id='app-tab-'+key;
      b.dataset.auraTab=key;b.setAttribute('role','tab');b.setAttribute('aria-controls','app-'+key);
      const icon=el('span','aura-nav-icon',icons[key]);icon.setAttribute('aria-hidden','true');
      b.append(icon,el('span','',LABELS[key]));b.addEventListener('click',()=>activate(key,true));buttons[key]=b;nav.append(b);}
    document.body.append(nav);
    let active=null;const scrolls={home:0,signals:0,chart:0,more:0};
    function activate(key,push){if(!TABS.includes(key))key='home';
      if(active===key)return;
      if(active)scrolls[active]=window.scrollY;
      active=key;for(const name of TABS){const selected=name===key;
        panes[name].hidden=!selected;buttons[name].setAttribute('aria-selected',String(selected));buttons[name].tabIndex=selected?0:-1;}
      if(push)history.pushState({auraTab:key},'', '#app-'+key);
      window.scrollTo({top:scrolls[key]||0,behavior:'instant'});
      if(key==='chart')requestAnimationFrame(()=>{root.dispatchEvent(new Event('resize'));root.AuraChartTools?.refresh?.();});
    }
    nav.addEventListener('keydown',event=>{if(!['ArrowRight','ArrowLeft','Home','End'].includes(event.key))return;
      event.preventDefault();const current=TABS.indexOf(active);
      const index=event.key==='Home'?0:event.key==='End'?3:event.key==='ArrowRight'?(current+1)%4:(current+3)%4;
      activate(TABS[index],true);buttons[TABS[index]].focus();});
    root.addEventListener('popstate',()=>activate(resolveTab(location.hash),false));
    root.addEventListener('hashchange',()=>activate(resolveTab(location.hash),false));
    // Existing in-page anchor links must reveal the section before scrolling.
    main.addEventListener('click',event=>{const link=event.target.closest('a[href^="#"]');if(!link)return;
      const target=document.getElementById(link.hash.slice(1));const pane=target?.closest('.aura-tab-pane');
      if(!pane)return;activate(pane.id.slice(4),true);target.scrollIntoView({block:'start'});event.preventDefault();});
    activate(resolveTab(location.hash),false);

    const fmt=n=>Number(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    let requestNo=0;
    async function refreshHome(){const current=++requestNo;
      try{const response=await fetch('/api/preview/signals/snapshot',{credentials:'same-origin',cache:'no-store',redirect:'error'});
        if(!response.ok)throw Error('HTTP_'+response.status);
        const data=await response.json();if(current!==requestNo)return;
        let threshold=50;try{threshold=new root.Aura5Confidence.LocalJournal(localStorage).threshold;}catch{}
        paint(homeState(data,Date.now()/1000,threshold,root.Aura5Confidence?.usable));
      }catch{if(current===requestNo)paint({state:'STALE',quote:null,reason:'Нет связи с наблюдателем или отсутствует доступ к данным'});}}
    function paint(model){badge.dataset.state=model.state;
      badge.textContent=model.quote?'LIVE · BITGET':'STALE · НЕТ LIVE';
      quote.textContent=model.quote?'Bid '+fmt(model.quote.bid)+' · Ask '+fmt(model.quote.ask):'Bid — · Ask —';
      updated.textContent=model.quote?'Источник Bitget · '+model.frame+' · получено '+new Date(model.quote.received_at*1000).toLocaleTimeString('ru-RU',{timeZone:'UTC'})+' UTC':'Проверьте соединение. Исторические свечи не считаются LIVE.';
      signal.dataset.state=model.state;
      signal.textContent=model.state==='WATCH'?(model.candidate.direction+' · WATCH · '+model.candidate.score+'/100'):model.state;
      details.textContent=model.state==='WATCH'
        ?'Entry '+fmt(model.candidate.entry)+' · SL '+fmt(model.candidate.sl)+' · TP '+fmt(model.candidate.tp)+' · net RR '+model.candidate.net_rr.toFixed(2)+' · '+model.reason
        :model.reason+(model.state==='WAIT'?' · Порог '+model.threshold+'/100':'');
    }
    refreshHome();const timer=root.setInterval(refreshHome,4000);
    root.addEventListener('pagehide',()=>root.clearInterval(timer),{once:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',build,{once:true});else build();
})(typeof window !== 'undefined' ? window : globalThis);

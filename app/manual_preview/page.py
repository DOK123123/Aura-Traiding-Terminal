"""Reuse the actual manual UI; exclude all retired/automatic account panels."""
from html.parser import HTMLParser
from html import escape
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
ASSETS=frozenset({'styles.css','aura-analyst.css','aura-analyst.js',
    'vendor/lightweight-charts.standalone.production.js','active43-live.js','live.js',
    'aura-scenario-journal.js','aura-chart-tools.js','app.js','aura-workspace.css',
    'manual-paper.css','manual-paper.js','manual-live.css','manual-live-analysis.js',
    'manual-live-feed.js','manual-live-ui.js','preview-status.js','favicon.svg'})


def page(ws_token=''):
    source=(ROOT/'static/index.html').read_text()
    marker='  <section class="panel scenario-journal"'
    if source.count(marker)!=1:raise ValueError('PREVIEW_PAGE_STRUCTURE_CHANGED')
    source=source[:source.index(marker)]
    # app.js starts loading immediately: its history parser must already exist.
    app_script='  <script defer src="/static/app.js"></script>'
    source=source.replace(app_script+'\n','')
    feed_script='  <script defer src="/static/manual-live-feed.js"></script>'
    source=source.replace(feed_script,feed_script+'\n'+app_script)
    source=re.sub(r'<script[^>]+src="/static/([^\"]+)"[^>]*></script>',lambda m:m[0] if m[1] in ASSETS else '',source)
    source=re.sub(r'<link[^>]+href="/static/([^\"]+)"[^>]*>',lambda m:m[0] if m[1] in ASSETS else '',source)
    source=source.replace('<body data-live-manual="true">','<body data-live-manual="true" data-manual-preview="true"><p class="analyst-warning" role="status">ИЗОЛИРОВАННЫЙ PREVIEW · отдельный виртуальный счёт · не production. Вход и ручное закрытие только после подтверждения. SL/TP разрешаются при открытии и выполняются автоматически только пока сервер работает.</p>')
    source=source.replace('<title>Aura Trading Terminal — Bitget BTCUSDT Futures</title>','<title>ISOLATED PREVIEW · Aura Live Manual Trader 5.0</title>')
    source=source.replace('</head>','<meta name="aura-preview-ws-token" content="'+escape(ws_token,quote=True)+'"><script defer src="/static/preview-status.js"></script></head>')
    source=source.replace('<main>','<main><section class="panel"><button id="preview-check" type="button">Проверить preview · только чтение</button><p id="preview-check-result" role="status">Изоляция БД ещё не проверена. Manual Paper выключен по умолчанию.</p></section>',1)
    # The shared chart writes this timestamp during reset AND every render.
    # The original footer was below the excluded panels; preserve its DOM contract.
    source+='\n<footer><span>PREVIEW ONLY · нет Active43, scheduler и реальных ордеров</span><span id="last-updated">Данные ещё не загружены</span></footer></main></body></html>'
    if '/api/active43' in source or 'id="active43-panel"' in source:raise ValueError('PREVIEW_PAGE_SCOPE_ERROR')
    return source

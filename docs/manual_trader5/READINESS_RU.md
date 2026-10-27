# Aura Manual Trader 5.0 — проверка интеграции, Issue #60

## Поведение

Единая рабочая область: LIVE Bitget → AURA ANALYST LONG/SHORT/WAIT → редактируемый ручной план → серверный предварительный расчёт → отдельное подтверждение → отдельный виртуальный счёт, позиция и журнал. Кнопка ANALYST только копирует уровни; события аналитика и таймеры не открывают позиции. Самостоятельный план явно отделяется от скопированного сценария.

Каждое ручное OPEN/CLOSE имеет модальное подтверждение с отменой. SL/TP — заранее выбранные пользователем защитные виртуальные выходы: работающий сервер проверяет их каждые 5 секунд. Они не требуют нового подтверждения на каждом тике. Автоматических входов нет.

## Источники и состав

- main `2154094`: PR #58, AURA ANALYST, LIVE, разметка и отдельный локальный notebook. Формулы и пороги ANALYST не изменены.
- PR #57 `3482335`: отдельный Manual Paper API, Decimal ledger, SQLite/Supabase storage, owner/CSRF, постоянные idempotency receipts и PostgreSQL harness.
- PR #59 `1fedbf1`: изолированный offline replay, тесты и исходные исследовательские отчёты перенесены без изменения торговых правил. 1 историческая сделка не доказывает преимущество. Replay не вызывается web-приложением.
- Изменения интеграции: lifecycle обоих сервисов; положение ручной панели рядом с ANALYST; read-only POST `/api/manual-paper/preview`; необязательные ограничения `entry_limit` и `analyst_at`; модальное подтверждение; Web Locks и восстановление неизвестного результата; browser harness.

## Расчёты и защита

- Виртуальный начальный баланс 10 000 USDT; одна BTCUSDT USDT-M Futures позиция, без плеча; notional ≤ min(2000, balance).
- Decimal: риск = abs(entry − SL) × quantity + fee(entry) + fee(SL), ≤0,5% текущего баланса. Комиссия ledger 0,06% на сторону. Новые входы запрещены при балансе ≤9000 USDT.
- LONG: ask → bid; SHORT: bid → ask. Gross, обе комиссии, Net и equity проверены независимыми значениями. Журнал и баланс сохраняются атомарно. Гэпы не обрезаются по рассчитанному риску.
- `Entry` — предел неблагоприятной цены рыночного виртуального исполнения: максимум LONG / минимум SHORT, не лимитная заявка. После preview предел дополнительно сужается до показанной серверной цены; неблагоприятное изменение требует повторной проверки. Сервер заново получает котировку и проверяет риск.
- Quote ≤5 секунд, фиксированные публичные Bitget GET, серверное время, source/product/bid/ask/top-of-book size. Нет биржевых ключей и order API.
- Скопированный сценарий проверяется сервером по generated_at, TTL, закрытию 5m, стороне, SL/TP и зоне входа. WAIT/429/history mismatch убирают пригодный сигнал. Истечение проверяется внутри SQLite-транзакции; PostgreSQL использует более строгий quote_ms, ограниченный deadline сценария, и проверяет его после ожидания SQL lock. Схема/RPC из #57 не изменены.
- Read-only preview не создаёт счёт, позицию или receipt. Чтение `/state` сохраняет первоначальный виртуальный счёт, как в #57.
- Потерянный ответ: исходное намерение сохраняется ДО отправки; тот же request ID возвращает первоначальную квитанцию даже после истечения сигнала. Другой intent с тем же ID отклоняется. Web Locks не дают вкладкам перезаписывать неизвестный результат. Повреждённый ключ блокирует новые операции. Reload никогда сам не отправляет команду.
- Owner Basic Auth, same-origin/CSRF и no-store сохранены. Числа передаются строками, неизвестные поля запрещены. Ошибки безопасно отображаются через textContent; redirects запрещены. Секреты остаются только на сервере.

## Проверки

Локально: Python 2075 PASS, 4 opt-in PostgreSQL NOT RUN; JavaScript 287 PASS. AST всех app/scripts/research/tests, import app.main, JS syntax, diff whitespace: PASS. Python 3.12.14; direct runtime packages соответствуют requirements.txt; certifi 2026.10.23 вместо CI 2026.7.22, Node 24.22.1 вместо CI 24.19.0. Есть прежнее предупреждение Starlette/anyio.

Новые тесты: preview без записи и независимые LONG/SHORT расходы, owner/CSRF, риск/размер, позиция, предел цены, WAIT/TTL/изменённый сценарий/вне зоны, deadline при ожидании lock, replay успешного intent после ошибки источника, независимый ручной план, cleanup failure, cancel/confirm/double click, потерянный ответ/reload, конфликт вкладок и повреждённое локальное хранилище. Отдельно проверена эксклюзивная миллисекундная граница TTL в SQL.

Полный Regression CI запускает все Python/Node suites, четыре disposable PostgreSQL harnesses и реальный Chrome desktop/mobile. Точный SHA и фактический результат — в описании PR. Browser screenshots и report.json сохраняются в артефакте Regression CI, в `manual-trader5-browser/`.

Локальная браузерная проверка **NOT RUN**: бинарный Chrome найден, но среда запрещает необходимый UNIX socket (`Operation not permitted`). Это не считается PASS. Браузерный CI обязателен: используется полный текущий HTML/JS, настоящий LWC, loopback FastAPI и настоящий SQLite, синтетические котировки, zero external network. Проверки: touch 393×851, desktop 1440×1000, OPEN/CLOSE, отмена, PnL/fees, reload, потерянный ответ/retry, protective SL gap, WAIT/429/history mismatch, stale quote, 401 и отсутствие Active43 writes. Физический Android не проверен.

Локальный стресс-тест холодного старта SQLite: **20 новых файлов × 16 одновременных OPEN**, каждый раз ровно одна позиция/квитанция, остальные запросы отклонены POSITION_ALREADY_OPEN. SQLITE_BUSY/LOCKED повторяет только начальную настройку WAL в пределах 10 секунд; торговая транзакция не воспроизводится этим циклом. Отдельный тест принудительно создаёт такую блокировку.

## Отдельные code / security review passes

Code pass: прослежены публичный analyst → copy → preview → confirm → authenticated API → quote → Decimal → SQL transaction/receipt → state/history; альтернативные WAIT, timeout, repeat и cleanup ветви. Исправлены конфликт lifespan при объединении #57/#58, устаревший copied signal, возможное движение цены после preview и перезапись pending другой вкладкой, миллисекундная граница TTL в SQL и конкурирующее включение SQLite WAL при холодном старте.

Security pass: проверены credential boundaries, owner/CSRF/scheme, schema/extra fields, safe DOM, no redirects, permanent request identity, transaction freshness и fail-closed storage. Нет подтверждённых нерешённых Critical/High в изменённой интеграции. Тестовые серверы не импортируются production и слушают только 127.0.0.1. Неизменённые legacy Active43 modules не подвергались новому полному аудиту.

## Настройка для последующего отдельного выпуска

В этом PR настройки не применяются, SQL не запускается, production не читается и не изменяется. Для будущего выпуска остаётся конфигурация #57:

- `AURA_MANUAL_PAPER_ENABLED=true` — отдельный opt-in только для этого виртуального счёта.
- `AURA_MANUAL_PAPER_STORAGE=supabase`, `AURA_MANUAL_PAPER_SUPABASE_URL`, серверный `AURA_MANUAL_PAPER_SUPABASE_SERVICE_KEY`; либо проверенный persistent-disk path. Без правильной конфигурации сервис закрыт; fallback на ephemeral SQLite отсутствует.
- Существующий `AURA_TESTNET_VIEW_PASSWORD` ≥12 символов; HTTPS для Web Locks/owner auth. Ключи в frontend или чат не передавать.
- Dedicated SQL `scripts/manual_paper_schema.sql` из #57; необходимости в новой миграции нет. Состояние действующего SQL и текущие env в этой задаче не проверялись и не изменялись. Не применять повторно без release review.
- Бесплатный Render + выделенные Supabase tables допустимы в рамках квот; постоянный Render disk нужен только для SQLite. Конфигурация и фактическая live gateway/quote проверяются отдельно перед разрешённым deploy.

## Ограничения

Комиссии ANALYST/notebook (0,10% + 0,05% adverse slip) отличаются от виртуального ledger (0,06%, наблюдаемый bid/ask); интерфейс это обозначает, notebook не является журналом исполненных сделок. Funding и полный стакан не моделируются, реальное проскальзывание сверх наблюдаемого bid/ask не доказано. При сне Render/недоступности источника SL/TP задерживаются; это не гарантия ограничения убытка. Preview — оценка, закрытие запрашивает новую цену.

Нет merge PR/main, deploy, изменения production/Render/Supabase/Cloudflare, включения Active43/PAPER или реальных торговых команд. Только изолированные синтетические виртуальные операции в тестах. Этот документ не является разрешением на выпуск или торговлю.

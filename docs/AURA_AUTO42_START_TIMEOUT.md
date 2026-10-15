# Aura 4.2 — отказ START при timeout анализа

База: 2ee8df134110387e94258b2b3f74f8834d61b92d, 15 октября 2026.

## Установленная причина и пределы доказательства

START выполняет preflight до записи режима ON. MarketContext может вернуть
ANALYSIS_TIMEOUT в двух разных случаях:

1. segment_states превышает собственный deadline COMPUTE_SECONDS=8;
2. snapshot waiter истёк через FETCH_SECONDS+COMPUTE_SECONDS+2 (22 секунды),
   хотя shielded shared refresh продолжает работать. Исторические analog queries
   выполняются после analyze_window и не входят в его восьмисекундный deadline.

При любом таком отказе до commit ON портфель обязан остаться OFF. Поэтому OFF
после reload — безопасный отказ активации, а не доказательство потерянного ON в
Supabase. Ошибка операции раньше подменяла диагностику владельческого режима:
error response не содержал прочитанный state/revision/saved_at, diagnostics()
получал state=None, frontend мог терять баланс/метки и показывать ERROR вместо
понятного «START отклонён, портфель остался OFF».

Какой из двух тайм-аутов происходил в конкретном Render-процессе, без его
авторизованных свежих diagnostics/logs не установлено. Не заявляется, что
лимит вычислений на Render подтверждён локальным benchmark или уже устранён.

## Изменения

- app/automated/market_data.py: если snapshot waiter вернул ANALYSIS_TIMEOUT,
  но общий task ещё работает, один раз ждём именно его ещё максимум 12 секунд
  через shield. Новый расчёт не запускается и общий task не отменяется.
  Затем результат проходит исходную проверку свежести в snapshot и strategy.
  Если реальный worker уже завершился timeout/error — дополнительного retry нет.
  Если добавочный бюджет исчерпан — остаётся отказ. Это исправляет ранний отказ
  ожидающего START, но не обещает ускорения CPU или успешности любого запроса.
- Сохраняются outer budgets START 45 s и tick 55 s; frontend 60 s. Медленная БД
  также расходует outer budget. Проверки безопасности не заменяются ожиданием.
- app/automated/service.py: запоминает последнюю фактически прочитанную envelope;
  при ошибке сохраняет safe activation_error и market diagnostics. Возвращается
  последний подтверждённый mode/revision/balance/saved_at с fresh=false,
  а не фиктивный успех. При успешном control ошибка активации очищается.
- diagnostics.market.error_source различает ANALYSIS_WAIT, ANALYSIS_COMPUTE и
  ANALYSIS_UNCLASSIFIED, analysis_task показывает RUNNING/IDLE. Это наблюдение
  задачи, не выдуманное доказательство CPU starvation.
- app/automated/api.py: защищённый control error response содержит snapshot
  прочитанного состояния; HTTP остаётся ошибочным, paper_only и запрет exchange
  execution сохраняются. Ни один отказ START не записывает ON или fake trade.
- static/auto42.js: failed START сохраняет метки/баланс, показывает отказ и OFF;
  после GET/reload в том же серверном процессе последняя activation_error остаётся
  в сообщении. Системный mode берётся из owner_mode, error выводится отдельно.
  Equity при отказе не объявляется свежим; START требует повторного GET.

Последняя activation_error хранится в памяти сервиса, не в торговом состоянии.
После рестарта диагностическая ошибка может исчезнуть; сохранённый портфель
в БД не исчезает. Не записываем ошибку START в финансовый state или историю
как состоявшуюся команду. При DB failure envelope — последнее известное чтение,
не подтверждение текущего состояния БД: fresh=false, failed UI, BLOCKED остаются.

Historical Pattern, структура/параметры стратегии, риск, freshness gates,
шаблоны SL/TP, versioned MarketContext/analogs и Supabase schema не менялись.
Не повышался deadline вычисления и не отключалась проверка artifact hash.

## Регрессии

- pending shared analysis завершился после первого waiter timeout → тот же task
  дождались один раз, новый refresh не создавался;
- уже завершившийся worker timeout не превращается в успех;
- добавочное ожидание ограничено, общий task не отменяется;
- START с ANALYSIS_TIMEOUT → HTTP503, mode OFF, баланс/диагностика сохранены,
  ревизия/история/портфель неизменны; последующий GET всё ещё показывает отказ;
- после восстановления данных новый явный START → ON → TICK → ON → RESTART → ON;
- frontend сохраняет OFF и баланс на ошибке и последующем refresh.

Фикстуры synthetic только для regression, не для оценки доходности. Тестовые
START исполняются в отдельных SQLite ledger с dummy credentials/ASGI transport,
не обращаются к production или реальным биржевым endpoint.

## Production и развёртывание

Production START агент не выполняет. Нельзя объявлять работу Render подтверждённой
прохождением этих тестов. Для применения требуется Deploy нового main на Render;
если включён Auto-Deploy, он может выполниться самостоятельно после push.
После обновления следующий явный START владельца должен либо подтвердить ON
и затем тот же ON после status/tick, либо сохранить OFF с конкретной причиной.
При повторном отказе диагностика различает worker compute limit и pending waiter.
Если подтверждён ANALYSIS_COMPUTE, необходим отдельный доказательный performance
fix по реальным safe timings Render; текущий commit не обещает исправить этот вид
отказа и не разрешает обход freshness или запуск без данных.

Cloudflare вызывает только tick, не START. Его настройки и секреты не менялись.
Supabase ON не сохраняется при неуспешном preflight по замыслу; после успешного
START атомарность/CAS/idempotency и restart persistence остаются прежними.

## Результаты проверок и ограничения

- Полный Python suite: 1123 passed, 0 failed, 1 Starlette/AnyIO deprecation
  warning, 78.71 s. После уточнения сохранения saved_at дополнительно прошли
  31 целевых Python regression и 20 tests Auto42 frontend.
- Все 11 JS suites: 167 passed, 0 failed.
- Python AST, import app.main, JS syntax: PASS.
- Статический scan credential signatures/exchange-write endpoints изменённых
  файлов: без совпадений. Никаких реальных credentials не читалось.
- Code/security review: изменение только ожидания существующего task и safe
  error snapshot; owner auth/CSRF, revision CAS, STOP priority, freshness/risk
  guards не сняты. Нет новых внешних клиентов или SQL migrations.
- Production публично: /api/health HTTP200; /api/auto42/status без owner auth
  HTTP401. Это не проверка production START, Supabase write или compute latency.
- Авторизованный production START и Android browser: NOT RUN. Настройки
  Cloudflare/Render account недоступны подключёнными инструментами.

Изменённые файлы: app/automated/market_data.py, app/automated/service.py,
app/automated/api.py, static/auto42.js, tests/test_auto42_start_timeout.py,
tests/test_auto42_frontend.cjs, docs/AURA_AUTO42_START_TIMEOUT.md.

Команды из корня:

```sh
python -m pytest -q
for file in tests/*.cjs; do node "$file" || exit 1; done
node --check static/auto42.js
python -c 'import app.main'
```

Cloud Python-прогон: PYTHONPATH=/workspace/ecc-audit-deps:$PWD,
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, python -B, enable_sandbox_poll() из
scripts/replay_aura_csv.py и pytest.main(['-q','-p','no:cacheprovider','--tb=short']).
Production event loop не менялся. Новых dependencies не добавлялось.

Дополнительная проверка неизвестного исхода: REQUEST_TIMEOUT/сбой во время commit
не считается доказанным отказом активации. Старый snapshot — последнее известное
состояние; UI требует перечитать сервер и не утверждает, что режим остался OFF.
Явное сообщение об отклонении OFF относится только к совпадающей диагностике
ошибки preflight. Добавлен отдельный JS regression; финально все 167 JS PASS.

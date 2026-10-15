# Aura Auto Paper 4.2 — согласованность режима и панелей

Дата: 15 октября 2026. База main: b2f6374739544543d50b541bf970a22ff78403af.

## Подтверждённая первопричина

В одной странице два независимых контроллера были названы «Авто Paper».
Нажатие верхнего «Запустить Авто Paper» включает не Aura 4.2, а старый
Historical Pattern. Поэтому верхнее ON и нижнее OFF не являются разными чтениями
одной строки Supabase. Активация другой системы не должна включать Aura 4.2.

| Панель до исправления | Frontend | API | Хранилище | Сигнал / исполнитель |
|---|---|---|---|---|
| Верхний «Авто Paper» | static/paper.js | /api/paper/state?scope=AUTO; POST /api/paper/auto | SQLite PAPER_DB_PATH, по умолчанию .data/paper.sqlite3 | Historical Pattern, app/paper/ |
| Нижний «4.2» | static/auto42.js | /api/auto42/status; POST /api/auto42/control | отдельный Supabase AURA_AUTO42_SUPABASE_* | MarketContext / confirmed structure retest, app/automated/ |

Оба сервиса независимо создаются в app/main.py lifespan. Они не используют
одну стратегию, баланс, финансовую политику или историю. Внешний Cloudflare Worker
и GitHub client обращаются только к /api/auto42/tick. Балансы 10 000 USDT могут
численно совпадать: это не доказательство одного портфеля.

Отдельная причина неуспешного нижнего START в конкретной production-сессии
не установлена: нет авторизованного ответа /control и кода отказа. Не заявляется,
что кнопка записывала ON и его потом отменял scheduler. Доказательств такого
перезаписывания нет. Скрывать или принудительно менять OFF в ON было бы ошибкой.

## Исправление

- Aura 4.2 перенесена выше локального Paper и стала основным открытым блоком.
  Её режим, метрики и диагностика читаются только из /api/auto42/status.
- Основной открытый блок при загрузке страницы выполняет только защищённый GET.
  Он не включает режим. START/STOP сохраняют существующий owner/CSRF/revision
  контракт, подтверждение и последующее повторное чтение состояния с сервера.
- Кнопки явно названы «Запустить Aura 4.2 · START PAPER» и
  «Остановить Aura 4.2 · STOP PAPER». Подтверждение называет портфель Supabase.
- Прежний локальный Paper / Historical Pattern сохранён в отдельном сворачиваемом
  разделе со своей стратегией, режимом и историей. Его реальные controls и API
  не перенаправлены на другой портфель. Названия запуска/возобновления и текст
  подтверждения прямо указывают Historical Pattern / SQLite, а не Aura 4.2.
- Режим прежнего движка остаётся виден в summary свёрнутого раздела. Работающий
  старый режим не скрывается и не останавливается агентом. Есть ссылки между
  разделами; важные предупреждения основного режима видимы.

Не менялись backend runtime, правила signal/SL/TP/risk, БД, credentials, workflow
или Worker. Не объединялись баланс и история; не мигрировались состояния ON/OFF.

## Сохранение и scheduler

Auto42 START загружает Supabase state/revision, выполняет preflight, записывает ON
и ACTIVATION_BASELINE через transactional commit. Status загружает state и строит
diagnostics из того же объекта. Tick при успешных свежих данных не меняет ON в OFF.
OFF возникает через owner STOP/RESET; временные data errors используют PAUSED,
а состояние ERROR в diagnostics отражает отказ. Нельзя считать это скрытым STOP.
При OFF/OWNER_STOP scheduler не возобновляет режим сам. При отсутствии позиции
heartbeat не продвигает watermark. STOP/EMERGENCY и риск остаются обязательными.

Разные scheduler могут выполнить параллельные HTTP, но существующие singleflight,
CAS, SQL row lock, operation key и candle watermark не допускают двойного входа.
В этой задаче не добавляются новые блокировки или новый финансовый engine.

## Тесты

Новые пять offline API integration regressions используют два реальных отдельных
SQLite ledger и production FastAPI routes с dummy owner/scheduler credentials:

1. START Historical Pattern не записывает Auto42 и не включает его.
2. START Auto42 → ON → status → tick → restart сохраняет ON; legacy не меняется.
3. STOP → OWNER_STOP → heartbeat/restart остаётся OFF, даже при legacy ON.
4. STOP legacy не меняет Auto42 ON или журнал.
5. Валидный synthetic signal → next closed candle → restart/repeated tick
   создаёт ровно одну Auto42 position и ни одной legacy-записи.

Финансовые fixture-данные применены только в offline tests. Production-сигналы
не подделывались. PostgreSQL и реальная одновременная запись Supabase в этих
тестах не запускались.

Frontend regression проверяет порядок и явные имена разделов, отсутствие
автоматического START при reload, read-only GET открытой панели, сохранение
Auto42 ON после refresh и OFF после STOP, отсутствие вызовов legacy API из
основного controls, видимый legacy badge в summary и отсутствие дубликатов ID.

## Production: фактически выполнено

- GET /: HTTP 200; страница содержит обе старые кнопки, legacy расположен раньше
  Auto42. Это подтверждает наблюдаемую двусмысленность интерфейса.
- GET /api/auto42/status: 401 без owner auth.
- GET /api/paper/state?scope=AUTO: 401 без owner auth.
- Новых production START/STOP/RESET/tick в рамках этой задачи агент не отправлял.
- Cloudflare account/logs/settings и Render Environment недоступны имеющимися
  подключениями. Их конфигурация или текущий ON не объявляются проверенными.
- Статус ON в конкретной Supabase row, продовый restart/reload и реальные
  scheduler ticks после START не проверены. Node DOM tests не заменяют Android.

## Развёртывание владельцем

Развернуть новый main на Render и обновить страницу. Если настроен Auto-Deploy,
проверить завершение его deploy; агент отдельный deploy не запускал.
Проверить, что первым идёт Aura 4.2, а Historical Pattern подписан отдельно.
Авторизоваться и обновить состояние основного блока. При явной команде владельца
START основного блока должен либо показать ON после серверного чтения, либо
показать конкретную ошибку preflight/сохранения. Подтверждённый отказ не скрывается.
В этой задаче агент START не выполняет. Не нажимать RESET для восстановления UI.

Ручная проверка Android: ширина 320–430px, сворачивание старого раздела, видимость
его badge, доступность START/STOP и предупреждений, сообщение ошибки, reload,
следующий scheduled tick; режим должен относиться к одному выбранному портфелю.
Если legacy ранее включён, его нужно оценивать отдельно: STOP Aura 4.2 не является
командой остановки Historical Pattern. Это необходимо для сохранения изоляции.

## Итог проверок перед commit

- Полный Python suite: **1119 passed**, 0 failed, 1 Starlette/AnyIO deprecation
  warning, 77.78 s.
- Все 11 Node suites: **165 passed**, 0 failed.
- Python AST, import app.main, node --check для обоих изменённых JS: PASS.
- HTML parser: 270 уникальных ID, дубликатов нет.
- Статический поиск credential signatures/private exchange-write endpoints
  в изменённых файлах: совпадений не найдено. Это не полная внешняя security-аудит
  инфраструктуры; реальные ключи не читались.
- Независимый review второго агента: UI/API isolation, owner confirmation,
  STOP/EMERGENCY priority, stale response handling, видимый legacy badge: PASS,
  блокирующих замечаний нет. Android и protected Render: NOT RUN.

Файлы:
static/index.html; static/paper.js; static/auto42.js;
tests/test_auto42_frontend.cjs; tests/test_auto42_mode_isolation.py;
docs/AURA_AUTO42_MODE_CONSISTENCY.md.

Воспроизведение:

```sh
python -m pytest -q
for file in tests/*.cjs; do node "$file" || exit 1; done
node --check static/paper.js
node --check static/auto42.js
python -c 'import app.main'
```

Cloud-прогон использовал уже установленные pinned зависимости через
PYTHONPATH=/workspace/ecc-audit-deps:$PWD, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1,
python -B, enable_sandbox_poll() из scripts/replay_aura_csv.py и
pytest.main(['-q','-p','no:cacheprovider','--tb=short']). Production loop не менялся.

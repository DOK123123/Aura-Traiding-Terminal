# Aura Intelligence 4.1: перспективная проверка прогнозов

## Фактический статус

Реализованы код, изолированный журнал, owner-панель и выключенный по умолчанию внешний scheduler. Реальные forward-прогнозы в этой сессии не собирались. Supabase, GitHub Actions и Render не настраивались и не проверялись live. ПРОВЕРКА ЕЩЁ НЕ ЗАВЕРШЕНА. При отсутствии конфигурации панель сообщает об этом; торговых решений система не разрешает.

База: `600e359e96a1078f9cd9913b591c8a7236f769fe`. Алгоритмы 4.0, artifact, предыдущие отчёты, Auto Paper, авторизация владельца и risk rules сохранены. Новая система только измеряет качество прогнозов; никаких методов биржевого исполнения и путей к Paper execution в ней нет.

## Архитектура и причинность

`app/forward/models.py` определяет неизменяемые записи, хэши, временную политику и исходы; `storage.py` — SQLite для разработки и Supabase RPC; `service.py` — capture/evaluation; `stats.py` — scoring; `api.py` — защищённые маршруты. Подключение жизненного цикла находится в `app/main.py`. Панель реализована в `static/forward_validation.js`.

Источник — существующий Binance Spot market context, BTCUSDT, 15m/1h/4h. Свечи закрытые, UTC; время журнала в миллисекундах, существующие Bar timestamps в секундах. Старшие свечи составляются только из полных UTC-блоков. Capture разрешён после закрытия анализируемой свечи и до закрытия первой будущей свечи. Дополнительно сервер БД проверяет собственное время при вставке. Исторического backfill нет: пропущенные capture нельзя задним числом заполнить архивом.

Запись содержит цену, source/timeframe, режим, структуру, индикаторы, MTF, выборку аналогов, распределение прогнозов, причинные baselines, версии, хэши конфигурации и исходных свечей. Модель 4.0 с недостаточной выборкой возвращает ABSTAINED; пороги не ослабляются. Cohort зависит от artifact, версии модели и исходного кода/политики forward. Разные cohort никогда не объединяются в оценке.

Исходы H=4/8/16/32 рассчитываются на точном закрытии соответствующей будущей свечи. Любой отсутствующий интервал делает исход MISSING_CANDLES, без замены следующей свечой. Изменение исходной цены — SOURCE_CORRECTION. MFE/MAE берутся только из данного горизонта. Decimal используется для доходности и денежных цен. Доходность здесь — изменение цены, а не прибыль торговой стратегии.

Предсказания и исходы append-only: уникальные ID и ограничения, транзакции, блокировки конкурентных RPC, запрет UPDATE/DELETE. Повторная доставка не заменяет запись. Выявленное изменение сохраняется отдельным CORRECTION и исключает связанную запись из scoring. Полностью завершённые старые исходы не пересканируются постоянно; поздние невыявленные исправления источника остаются ограничением. Привилегированный администратор БД способен изменить схему: hash и triggers не заменяют независимого внешнего свидетельства.

## Безопасная настройка владельцем

Платные сервисы не создавались. Перед выбором бесплатного Supabase проверьте действующие квоты, условия и возможность приостановки проекта.

1. Создайте отдельный Supabase project для forward-журнала. Через SQL Editor выполните `scripts/forward_validation_schema.sql`. Реальное выполнение этого SQL в sandbox не проверено: PostgreSQL отсутствует. Требуются ручные RPC smoke-проверки до включения cron.
2. В Render Environment добавьте `AURA_FORWARD_SUPABASE_URL` (HTTPS projectref.supabase.co без пути), `AURA_FORWARD_SUPABASE_SERVICE_KEY` (server-only service key) и отдельный `AURA_FORWARD_SCHEDULER_SECRET` (случайная строка ASCII 32–256 символов). Scheduler secret должен отличаться от ключа БД и owner password. Существующий `AURA_TESTNET_VIEW_PASSWORD` сохраняется для owner GET.
3. Не добавляйте credentials в git, браузер, issue или логи. Supabase key хранится только на backend. RLS и закрытые grants запрещают anon/authenticated доступ; RPC доступны service_role. Не используйте этот project для paper-портфеля.
4. В GitHub Actions secrets добавьте только `AURA_FORWARD_TICK_URL=https://terminal.onrender.com/api/intelligence/forward/tick` и `AURA_FORWARD_SCHEDULER_SECRET`. Ключ БД и пароль владельца Actions не нужны.
5. Repository variable `AURA_FORWARD_ENABLED` оставьте выключенной до проверки схемы, приложения и секретов. Для запуска workflow установите `true`, выполните workflow_dispatch и проверьте COMPLETED, новую запись, дедупликацию повторного запроса и отсутствие секретов в логах. Затем оставьте расписание каждые 5 минут.
6. На Android откройте терминал, войдите через существующую owner authentication, раскройте панель forward validation. Проверяйте время последней записи, успешной оценки и пропущенные capture. Наличие scheduler-конфигурации не доказывает его фактическую работу.

GitHub cron best-effort: задержки, отключение неактивных расписаний, лимиты Actions и сон Render возможны. Непрерывная работа 24/7 не гарантируется. URL workflow намеренно ограничен terminal.onrender.com; другой домен требует отдельного review. Retries ограничены, redirects запрещены; сообщения ошибок не содержат credentials.

SQLite допускается только локально через `AURA_FORWARD_SQLITE_PATH` с именем `forward-validation.sqlite3`. На Render такой режим отвергается: ephemeral FS не является долговременным хранилищем. Одновременная local/remote конфигурация запрещена. При ошибке remote нет скрытого fallback в локальную БД. Чужая SQLite БД, включая Paper, не изменяется.

## Метрики и ограничения

Для одинакового набора FORECAST+COMPLETE сравниваются модель, unconditional, same-regime, simple-trend и no-change baselines. Считаются MAE/RMSE в процентных пунктах, accuracy знака, binary balanced accuracy при наличии обеих ненулевых классов, трёхклассовые Brier и log loss, calibration bins. Нулевая вероятность фактического класса даёт log loss INFINITY, без post-hoc clipping. ABSTAINED, повреждённые, исправленные и неполные исходы не выдаются за прогнозы.

Панель показывает глобальные счётчики отдельно от метрик текущей cohort по последним 100 prediction-записям; эти метрики помечены partial. Старые cohort доступны через owner API и полный export. Non-overlap count не равен эффективному размеру независимой выборки. Neff и confidence interval пока UNKNOWN/null: IID-интервалы не выдумываются. Формальной block-bootstrap оценки в 4.1 нет; вывод о наличии edge делать нельзя.

Время последней успешной оценки учитывает только COMPLETE исходы. Контроль пропущенных свечей и 5-минутных tick-слотов начинается с первой записи, не с предполагаемой даты запуска. Ограничения одного tick: 55 секунд, 50 pending predictions, пакет до 100 записей; backlog обрабатывается следующими вызовами. При разрыве процесса повтор безопасен, незавершённый run виден отдельно. Supabase RPC имеют ограничение времени, concurrency и размера ответа.

## Экспорт, резервирование и восстановление

Owner GET `/api/intelligence/forward/status` и `/export` защищены существующей Basic authentication. POST `/tick` требует отдельного `X-Aura-Forward-Token`; owner Basic сама по себе не разрешает запись. Нет ручного UI capture, удаления или замены прогнозов.

```bash
python scripts/export_forward_journal.py https://terminal.onrender.com forward.jsonl
python scripts/score_forward_journal.py forward.jsonl --output forward-scores.json
```

Пароль CLI читается из environment `AURA_TESTNET_VIEW_PASSWORD`, не из аргумента командной строки. Export фиксирует max sequence, проверяет целостность всех страниц и создаёт SHA256 manifest. Отказывайтесь от scoring неполного файла или отсутствующего manifest. Если запись manifest прервалась после записи JSONL, экспортируйте заново в новый путь. Не перезаписывайте прежние backups.

Offline CLI ограничен 250000 записями/512 MiB и держит данные в памяти; его следует запускать локально, не на Render. Регулярно храните проверенные копии независимо от проекта БД. Автоматический restore не реализован: восстановление делает администратор в отдельном проекте с проверкой counts/hashes и уникальных ID до переключения backend. Никаких восстановлений paper-портфеля этой системой не выполняется.

## Проверки и review

Полный Python suite: **1021 passed**, 1 предупреждение (53.93 s). Полный JavaScript: **140 passed**, 9 файлов. Новые проверки: 22 Python и 6 JS. Выполнены syntax/import проверки, проверка совместимости artifact 4.0, тесты prospective capture, точных горизонтов, пропусков, коррекций, restart, конкуренции, cohort, authentication, export, scoring и safe remote errors. Synthetic fixtures служат только проверке кода, не являются рыночными результатами.

Проведены отдельные проходы архитектуры, безопасности и математики по ECC/Aura guidance одним исполнителем; это не независимая проверка несколькими моделями. Исправлены connection lifecycle SQLite, race конкурентной вставки RPC, единая проверка scheduler-конфигурации и сохранение UI ошибки при переключении фильтров. Новых зависимостей нет. Logging guard защищает существующие handlers/lastResort; новая произвольная конфигурация logging должна сохранять redaction.

**Не выполнены:** реальное исполнение SQL/Supabase RPC, проверка durability внешней БД, GitHub cron, live Render, Android/browser layout и фактический сбор forward-периода. Для ручной проверки: ширина 320–430px, owner login/logout, один refresh при повторных касаниях, network timeout/восстановление, отсутствие endless spinner, точные времена UTC, ошибки storage, повтор tick без дубля, новый outcome после H=4 и отсутствие каких-либо paper/exchange ордеров.

Следующий шаг — настройка отдельного durable-хранилища и успешный manual smoke, затем накопление нового forward-периода. До этого статус исследования: NOT_CONFIGURED / ПРОВЕРКА ЕЩЁ НЕ ЗАВЕРШЕНА.

# Aura 4.3 Bitget: настройка и безопасная проверка

## Установленные факты

Проверено 2026-10-19, база — main `1254dbe` (PR #16 объединён).

- GitHub REST зарегистрировал workflow **389888954**, `state=active`, путь
  `.github/workflows/aura-active43.yml`. До исправления `total_count=0` запусков.
  Его отсутствие в конкретном экране Actions не означает отсутствия регистрации.
  [Прямая ссылка на workflow](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/workflows/aura-active43.yml).
- Job-level условие в main блокирует **и ручной запуск**, когда
  `AURA_ACTIVE43_BITGET_SCHEDULER_ENABLED=false`. Это исправлено: ручной режим
  `diagnostics` не зависит от переменной. Запуски `tick` по-прежнему требуют `true`.
- Сообщение `ACTIVE43_DISABLED` возникает до создания клиентов, если общий
  `AURA_ACTIVE43_ENABLED` отсутствует или выключен в старом main. Оно не является
  результатом проверки Bitget/Supabase. Без доступа к Render env нельзя установить,
  какой из этих двух случаев имеет место. Исправление допускает отсутствие старого
  флага при явном `AURA_ACTIVE43_BITGET_ENABLED=true`; явный общий `false`
  остаётся запретом. Сохранённый режим портфеля не меняется.
- Render `/api/health`: HTTP 200 `{"status":"ok"}`. Владелец API
  `/api/active43/status`: HTTP 401 без авторизации. Публичный active43.js имеет
  SHA256 `0920a1a209ec76b21bf0aa5a1c838f7809876e4b48b9fc57135ac57b5c155401`,
  совпадающий с main PR #16. Это подтверждает доступность приложения и frontend,
  **не** соединения с Bitget/Supabase или прохождение торгового цикла.
- GitHub API чтения variables/secrets вернул HTTP 403 `Resource not accessible
  by integration`. Секреты не запрашивались у владельца, их значения не читались.
  Доступа к Render management API/owner-паролю/Supabase credentials в сессии нет.

### Проверка настоящего GitHub Actions запуска

Вручную запущен **только** `operation=diagnostics` из интеграционной ветки:
[run 39339951183](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/39339951183).
GitHub принял YAML, checkout и условие диагностического job. Торговый шаг **skipped**.
Диагностический шаг завершился **FAIL — SCHEDULER_NOT_CONFIGURED**:
переменная `AURA_ACTIVE43_BITGET_SCHEDULER_SECRET` в этом job была пустой.
До HTTP-запроса дело не дошло. Это **не** ошибка Bitget/Render и не проверка
совпадения токенов. Репозиторий не имеет GitHub Environments (API вернул `[]`).
Чтение metadata secrets текущему GitHub-доступу недоступно (HTTP 403), правильного
Render token в сессии нет; безопасно записать его автоматически невозможно.
Нужно сохранить **тот же существующий Render token** в Repository Actions secret
с точным указанным именем; не публиковать значение и не передавать его в чат.
Сам workflow уже зарегистрирован, а прямой видимый запуск теперь существует.

## Что изменено

1. Кнопка **ПРОВЕРИТЬ ВСЮ СИСТЕМУ** в Owner Panel: защищённый
   `POST /api/active43/diagnostics`, owner Basic auth + существующая same-origin
   CSRF-защита. Работает при отключённом серверном модуле и PAPER OFF.
2. Для GitHub — отдельный `POST /api/active43/diagnostics/scheduler` с независимым
   Bitget scheduler token; owner-пароль и другие scheduler tokens не подходят.
   Один и тот же read-only модуль, без вызова `tick`, `control`, `advance`,
   `load`, `commit`, `OPEN` или `CLOSE`.
3. Bitget: публичные GET time/contracts/ticker/history, строгий USDT perpetual
   BTCUSDT, сверка спецификации, цены/времени и двух закрытых свечей каждого из
   15m/1h/4h. Это проверка соединения, **не** прогон всей стратегии.
4. Supabase: существующий history RPC и GET **только** singleton
   `aura_active43_bitget_account`, проверка checksum, scope/version/config.
   В отличие от `load`, GET не создаёт счёт. Отсутствующий счёт обозначается
   `NOT_INITIALIZED`, баланс остаётся `null`, а не подставляется 10000.
5. Scheduler ACTIVE означает недавний **сохранённый успешный tick** (≤360s)
   и корректно настроенный отдельный секрет. Доставка диагностического HTTP-запроса
   показывается отдельно; она не создаёт tick и не доказывает периодические запуски.
6. Результат содержит время проверки, признак Render и допустимый commit SHA,
   реальные прочитанные баланс/позицию, ошибки и только имена отсутствующих env.
   Не возвращает ключи, значения переменных, raw upstream errors/headers/URLs.
7. Параллельные проверки объединены в один task, кешируются 20s; Bitget и DB
   проверяются независимо, каждая в пределах 24s. Нет анализа стратегии/backtest,
   отдельные market connections не занимают lock торгового цикла. При остановке
   приложения task отменяется и клиенты закрываются.

## PostgreSQL / миграция

`active43_bitget_schema.sql` дополнен только `GRANT SELECT` на новую Bitget account
таблицу для `service_role`. RLS/запрет anon/authenticated сохранены, прямые права
INSERT/UPDATE/DELETE не добавлены. Таблицы/функции Aura 4.2, Practice, старых Spot43
и Bybit43 не изменены.

В существующем Supabase grant обычно уже предоставлен default privileges.
**SQL повторно применять без необходимости не требуется.** Если диагностика
успешно читает history, но сообщает `STORAGE_PERMISSION_DENIED` на account GET,
предусмотрен маленький дополнительный файл
[`scripts/active43_bitget_diagnostics_grant.sql`](../scripts/active43_bitget_diagnostics_grant.sql).
Он только предоставляет SELECT выделенной таблицы, без записи данных или
замены функций. Применение production SQL требует отдельного разрешения владельца.

Чтение не проверяет возможность записи commit RPC. Это подтверждается локальным
PostgreSQL, а на Render — только последующими сохранёнными OFF ticks и настоящими
сделками после разрешения владельца. Диагностика честно отдаёт `writes_tested=false`.

## Проверки и границы доказательств

Итоговые результаты и отдельные code/security review — в
[AURA43_SETUP_RESULTS.json](AURA43_SETUP_RESULTS.json).

- Python: полный набор с opt-in тестами настоящего локального PostgreSQL.
- JavaScript: все `.cjs` тесты, включая кнопку без загруженного портфеля.
- PostgreSQL 16 в временном Docker без сети: LONG/SHORT × TP/SL/оба, комиссии,
  проскальзывание, SQL rollback, неизвестный результат записи, конкурентные ticks,
  перезапуск настоящей БД. Дополнительно: GET пустого счёта не создаёт строки;
  чтение service_role разрешено, anon/authenticated запрещено; диагностика при
  открытой позиции после restart оставляет account/events побайтно неизменными.
  Хеши legacy account/event и определений SQL-функций до/после совпадают.
  HTTP-to-psql adapter выполняет настоящий SQL, но не доказывает hosted PostgREST/JWT.
- Chromium, mobile 430px: owner HTTP API, история и OPEN/CLOSE markers, отдельная
  кнопка диагностики; её выполнение сохраняет state/revision без изменения.
  Рыночные сценарии в этих тестах **синтетические, только локально**.
- YAML реально разобран PyYAML 6.0.2 во временном каталоге; зависимости приложения
  не изменены. GitHub регистрация старого workflow подтверждена REST; исполнение
  изменённого workflow определяется отдельно в итоговом отчёте.
- Настоящий Bitget из среды разработки: CONNECTED, цена/часы/контракт/закрытые
  15m/1h/4h проверены, записи в Supabase не выполнялись. Это **не Render**.
- Новая версия не merged/deployed. Production SQL, баланс, позиции, ON/OFF,
  GitHub scheduler variable и секреты не изменены.

`PRODUCTION_PAPER_VERIFIED = FALSE`: изолированный цикл и диагностика не дают
такого статуса. Для него нужны естественные SIGNAL → OPEN → UPDATE → CLOSE
на Render с сохранением соответствующих событий в Supabase.

## Запуск: два этапа владельца

### 1. Выпустить исправление, оставив торговлю OFF

1. После проверки итогового PR разрешить его merge в main (автоматически не выполняется).
2. На [Render Dashboard](https://dashboard.render.com/) открыть сервис Aura →
   **Manual Deploy → Deploy latest commit**; Auto-Deploy можно оставить выключенным.
3. Убедиться, что `AURA_ACTIVE43_BITGET_ENABLED=true`; старый общий флаг можно не
   добавлять, но если он явно `false`, его включение требует решения владельца.
   URL/key/token оставить существующими. Это разрешает модуль, а не PAPER ON.

### 2. Проверить соединения и затем отдельно разрешить PAPER

1. В [Repository Actions Secrets](https://github.com/DOK123123/Aura-Traiding-Terminal/settings/secrets/actions)
   сохранить `AURA_ACTIVE43_BITGET_SCHEDULER_SECRET` с тем же значением, которое
   уже настроено в Render. Затем [открыть терминал](https://aura-traiding-terminal.onrender.com/), войти владельцем,
   открыть Aura 4.3 → **ПРОВЕРИТЬ ВСЮ СИСТЕМУ**. Bitget/Supabase должны быть
   CONNECTED. При ошибке оставить PAPER OFF; панель покажет конкретную причину.
   Нажатие «Обновить» читает/инициализирует новый портфель через существующий load:
   новый счёт получает 10000 OFF, существующий не сбрасывается.
2. После успешной проверки разрешить внешний scheduler: в
   [Actions Variables](https://github.com/DOK123123/Aura-Traiding-Terminal/settings/variables/actions)
   установить существующую `AURA_ACTIVE43_BITGET_SCHEDULER_ENABLED=true`.
   Дождаться сохранённого OFF tick (обычно 5–10 минут; GitHub не гарантирует срок).
   Для ручной проверки в [workflow](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/workflows/aura-active43.yml)
   Run workflow → `operation=tick`; для проверки token/HTTP без записи выбирать
   `operation=diagnostics`, доступный также при variable=false.
3. Обновить диагностику после 20s: scheduler должен стать ACTIVE, balance 10000
   для нового счёта. Только тогда по решению владельца нажать **START EXPERIMENTAL
   PAPER** с подтверждением. Нет сигнала → нет сделки, причина видна в панели.

При явном ошибочном env/отсутствующих SQL правах могут потребоваться указанные
в панели точечные исправления; пока production недоступен для проверки, обещать
полностью автоматический запуск без этих условий нельзя.

## Остановка и эксплуатация

- STOP запрещает новые входы, но защитные выходы по открытой позиции требуют
  работающего scheduler. Не выключать серверный модуль/внешний scheduler при
  открытой позиции без понимания этой потери сопровождения.
- Бесплатный Render может спать; GitHub Actions может задерживать/пропускать
  scheduled jobs. Это не гарантированная инфраструктура 24/7. Paper SL/TP —
  виртуальные проверки свечей, а не стоп-ордера на бирже.
- Новых платных ресурсов/API, торговых Bitget credentials и private trading API
  не требуется. Ограничения существующих бесплатных Render/Supabase сохраняются.
- Стратегия, риск ≤0.5%, дневной лимит 2%, max notional 2000, одно открытие,
  исполнение/комиссии/проскальзывание не меняются. Прибыльность не обещается.

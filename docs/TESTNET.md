# Binance Spot Testnet — только чтение

Aura читает официальный Spot Testnet через фиксированный адрес
`https://testnet.binance.vision`. Продакшен-биржа для аккаунта недоступна,
переключателя адреса и fallback на реальные аккаунты нет. График BTCUSDT
продолжает использовать публичные рыночные источники: это отдельный модуль,
а не котировки Testnet для исполнения ордеров.

## Подключение в Render

1. Откройте [официальный Spot Test Network](https://testnet.binance.vision/).
2. Нажмите **Log In with GitHub**, войдите и разрешите авторизацию официального портала.
3. Создайте **HMAC-SHA-256 API Key**: для этой версии нужен ключ с API Key и Secret,
   а не RSA/Ed25519 с private key. Разрешение чтения аккаунта — **USER_DATA**.
   Не включайте TRADE, если портал позволяет выбрать разрешения.
4. Скопируйте Key и Secret в защищённое хранилище. Не отправляйте их в чат,
   файлы проекта или GitHub. Не используйте ключ обычного Binance-аккаунта.
5. Render → ваш Web Service Aura → **Environment** → **Add Environment Variable**:

   | Переменная | Значение |
   | --- | --- |
   | `BINANCE_TESTNET_API_KEY` | API Key официального Spot Testnet |
   | `BINANCE_TESTNET_API_SECRET` | Secret этого же HMAC-ключа |
   | `AURA_TESTNET_VIEW_PASSWORD` | Отдельный случайный пароль владельца, минимум 12 символов (рекомендуется 24+) |

6. Сохраните переменные с перезапуском/redeploy сервиса. Команда остаётся
   `python start_web.py`. Новые runtime-зависимости не нужны.
7. Откройте HTTPS-адрес Aura на телефоне. В блоке **TESTNET ACCOUNT** нажмите
   **Войти для просмотра Testnet**. В системном окне браузера имя — **aura**,
   пароль — `AURA_TESTNET_VIEW_PASSWORD`. Это пароль просмотра, а не ключ Binance.
8. После входа проверьте **Connected**, баланс по активам и открытые ордера.
   Пустой список ордеров нормален. Для истории укажите пару, например BTCUSDT
   или ETHUSDT, и нажмите **Показать историю**.

Активы Testnet виртуальные, перевод реальных денег не требуется и невозможен.
Binance периодически сбрасывает тестовую историю и ордера, примерно раз в месяц;
это может объяснить исчезновение истории.

## Что доступно

- `GET /api/testnet/account`: статус, balances (free/locked/total в единицах актива),
  активы с положительным свободным балансом, открытые ордера **всех пар**.
- `GET /api/testnet/history?symbol=BTCUSDT`: до 100 последних ордеров и 100 сделок
  одной выбранной пары, которые доступны в Testnet. Это не полный архив;
  официальный API требует symbol для allOrders/myTrades.
- `GET /api/testnet/login`: защищённый вход владельца с возвратом на главную.

Баланс не пересчитывается в USDT, позиции и PnL не рассчитываются.
Никаких методов создания/изменения/отмены ордеров, переводов, paper trading
или автоматического исполнения здесь нет. Режим read-only обеспечен в коде
независимо от разрешений ключа: только GET и закрытый список upstream endpoints
(time, account, openOrders, allOrders, myTrades).

## Состояния и сбои

- **Not configured**: Key или Secret отсутствует. Ни одного запроса Testnet;
  график, live-данные и анализ работают как прежде.
- **Disconnected / вход владельца**: API отвечает 401 до входа. Аккаунт не публичен.
- **Disconnected / просмотр закрыт**: ключи есть, но пароль просмотра отсутствует
  или короче 12 символов; аккаунт закрыт (403), рынок продолжает работать.
- **Connected**: последнее чтение account и openOrders успешно. Снимок обновляется
  раз в 60 секунд; это не поток аккаунта. Время проверки показано отдельно.
- Неверные ключи, timeout, потеря соединения, невалидные данные и недоступность
  вызывают безопасный Disconnected, очистку данных и автоматический повтор.
- 429/418: соблюдается Retry-After (число секунд или HTTP-дата), при отсутствии
  корректного значения — 60 секунд, максимум 24 часа. Общий cooldown для чтений.
- Время подписей синхронизируется с Testnet; при -1021 выполняется одна повторная
  синхронизация, бесконечного retry нет. -1121 означает недоступную пару.
- Устаревшие снимки на клиенте через 90 секунд скрываются; после возврата
  на вкладку приложение повторяет чтение. При ошибке старый баланс не сохраняется.

## Диагностика подключения на Render

Раньше `UNAVAILABLE` объединял сетевые исключения, большинство HTTP-ошибок
и неизвестные Binance codes. Такой ответ не устанавливает причину сбоя.
Теперь защищённый `/api/testnet/account` возвращает безопасный `diagnostics`:
только allowlisted `endpoint` (путь без query), числовые `http_status` и
`binance_code`, фиксированные категории `network_error`/`timeout_phase`, если
они доступны. Те же поля пишутся в Render Logs без raw response/exception.
Отсутствие HTTP status означает, что HTTP-ответ не получен, а не HTTP 200.

| Code Aura | Значение / действие |
| --- | --- |
| `NETWORK_ERROR` | DNS/TLS/connect/read/write/proxy/protocol; проверьте исходящий доступ Render. DNS/TLS выделяются только если transport сохранил тип причины. |
| `TIMEOUT` | Connect/read/write/pool timeout, общий timeout снимка или Binance -1007 (`UPSTREAM`). |
| `KEY_INVALID` | Binance -2014: неверный формат API Key. |
| `KEY_REJECTED` | Binance -2015: неверный ключ **или** IP-ограничение **или** permissions. API не позволяет однозначно различить эти причины. |
| `SIGNATURE_INVALID` | Binance -1022: подпись отвергнута; проверьте парный Secret и тип HMAC-ключа. |
| `PERMISSION_DENIED` | Binance -1002: чтение не разрешено; проверьте USER_DATA и IP restrictions. Не включайте TRADE для диагностики. |
| `AUTH_FAILED` | HTTP 401 без более точного Binance code. |
| `CLOCK_ERROR` | Binance -1021 после одной повторной синхронизации времени. |
| `RATE_LIMITED` | HTTP 418/429 или Binance -1003/-1015; соблюдается общий cooldown. |
| `REGION_RESTRICTED` | HTTP 451: ограничение доступа для региона/IP; это не доказательство неверного Secret. |
| `WAF_BLOCKED` | HTTP 403 без более точного code: возможна WAF/IP блокировка, не автоматически «неверный ключ». |
| `ENDPOINT_UNAVAILABLE` | HTTP 404/405/410 или Binance -1016/-1020. |
| `REDIRECT_BLOCKED` | HTTP 3xx: credentials не пересылаются по Location. |
| `UPSTREAM_UNAVAILABLE` | HTTP 5xx или Binance -1000/-1001/-1006/-1008. |
| `HTTP_ERROR` / `BINANCE_ERROR` | Другой HTTP error / отрицательный Binance code при HTTP success; смотрите числовые поля. |
| `INVALID_DATA` | Некорректный успешный ответ или невалидные данные аккаунта. |

После redeploy войдите владельцем и откройте `/api/testnet/account`; проверяйте
только `code` и перечисленные поля `diagnostics`, либо строку `Testnet read failed`
в Render Logs. Не копируйте signed URL, HTTP headers, raw bodies или credentials.
Старый баланс при любой ошибке скрывается; повтор выполняется после cooldown.

BASE URL остаётся официальным `https://testnet.binance.vision` с путями
`/api/v3/time`, `/api/v3/account`, `/api/v3/openOrders`. HMAC-SHA256 вычисляется
по URL-encoded query, ровно эта строка отправляется с appended signature;
timestamp — миллисекунды с поправкой `/time`, recvWindow — 5000 ms.

Если ключ ограничен IP, сверьте список с **Connect → Outbound** вашего сервиса
Render по [официальной инструкции](https://render.com/docs/outbound-ip-addresses).
Не отключайте TLS и не переключайте аккаунт на production. При HTTP 451 сначала
установите допустимость региона/доступа у Binance; эту внешнюю блокировку нельзя
исправить изменением подписи. Codex-сеть не является проверкой Render egress.
Без ответа/логов именно работающего Render-сервиса его конкретная причина
не подтверждена; offline tests проверяют классификацию и безопасность.

## Безопасность и ограничения

Binance credentials читаются только из Environment Variables сервером. Secret
используется для HMAC-SHA-256, API Key отправляется только официальному Testnet
через X-MBX-APIKEY. TLS проверяется, redirects запрещены. Ответы API строятся
по списку разрешённых полей; исходный текст Binance и исключений не возвращается
и не логируется. Логи httpx с подписанными URL подавляются, transport debug
отключён; сообщения с credentials/их exception traceback фильтруются.

Просмотр аккаунта защищён HTTP Basic, только через HTTPS Render. Сравнение
пароля выполняется constant-time. Пароль не встраивается в JavaScript и не
передаётся в URL; браузер использует стандартную авторизацию. Ответы API —
Cache-Control: no-store; CORS для чужих сайтов не включён. Пароль ≥12 символов
обязателен при настроенных ключах. Смена пароля/ключей требует перезапуска.
Никогда не добавляйте реальные credentials в проект: `.env`/`.env.*` исключены.

Снимки хранятся только в памяти процесса (TTL 60 с). После restart/redeploy
они читаются заново; торговый журнал этим этапом не создаётся. Один worker
сохраняет общий кэш/ограничение частоты. При нескольких workers/репликах потребуется
общий механизм rate limits. Basic-сессия браузера не имеет кнопки выхода:
для завершения используйте приватную вкладку/закройте её или очистите авторизацию.

## Проверка

`python -m pytest -q` — весь Python-набор, включая подписи, защиту аккаунта,
таймауты, rate limits, invalid keys, clock skew, кэш и отсутствие мутирующих API.
`node tests/test_testnet_frontend.cjs` и `node tests/test_frontend_reliability.cjs`
— интерфейс и прежняя надёжность рыночных данных. Node нужен только для этих тестов.
Все новые проверки используют MockTransport/фиктивные credentials и не обращаются
к Binance. Ни один тест не отправляет ордера.

В ограниченной среде Codex pytest 8.3.5 и его служебные зависимости взяты
из официальных исходников в /tmp, без изменения requirements.txt. Временный
тестовый event loop обходит блокировку служебного wakeup socket sandbox;
production event loop не изменён. Установленные здесь FastAPI/Starlette новее
pinned Render-версий: возможен deprecation warning TestClient, это не ошибка Aura.

## Официальные источники

Проверено 2026-10-11:

- [Testnet general info](https://developers.binance.com/en/docs/products/spot/testnet/general-info)
- [Testnet REST API: подписанные USER_DATA GET-запросы](https://developers.binance.com/en/docs/products/spot/testnet/rest-api)
- [Официальные Binance Testnet error codes](https://developers.binance.com/en/docs/products/spot/testnet/errors)
- [Spot Test Network: вход, виртуальные активы и сбросы](https://testnet.binance.vision/)

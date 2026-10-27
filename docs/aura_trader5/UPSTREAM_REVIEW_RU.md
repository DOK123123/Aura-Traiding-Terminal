# Технический и лицензионный аудит проектов · 2026-10-27

Проверены официальные GitHub repositories через read-only API: LICENSE, README,
package.json / pyproject.toml / setup.py. Точные immutable commit IDs, URL и
SHA-256 прочитанных файлов: `UPSTREAM_AUDIT.json`. Это инспекция исходных
манифестов и лицензий, не запуск/аудит всего чужого кода и не юридическое заключение.
Сторонний исходный код не копировался, пакеты не устанавливались/не вендорились.
Даты активности — свидетельство коммитов, не гарантия сопровождения или SLA.

| Проект / проверенный commit | Лицензия | Поддержка и зависимости | Совместимость и решение |
|---|---|---|---|
| [dylanpersonguy/OpenCharts](https://github.com/dylanpersonguy/OpenCharts/tree/d3fc63cc002e6e651801be6e952e7514e58fa5fe) `d3fc63c` | MIT собственного кода; отдельные Apache 2.0 notices для Lightweight Charts | Не архивирован; pushed 2026-10-14. package v0.3.0, React/DOM>=18.2, LWC ^4.2, Zustand, React Query, Radix, zod; TypeScript/Vite/Node>=20. Есть scripts typecheck/lint/vitest; здесь не выполнялись. | FastAPI можно подключить через data adapter, но это отдельное React-приложение и другая major LWC. Прямое внедрение в plain JS Aura/LWC 5.0.8 не оправдано. Ручные SVG-инструменты написаны заново, LIVE feed не заменяется. |
| [xgboosted/pandas-ta-classic](https://github.com/xgboosted/pandas-ta-classic/tree/9715f2445f0c39b79cf3dec5e2c341b89d69e182) `9715f24` | MIT | Community maintained, не архивирован; pushed 2026-10-23. Python>=3.11, numpy>=2, pandas>=2; TA-Lib optional; test/oracle extras отдельно. | Python 3.12/numpy2.2.6 Aura формально укладываются, но pandas не runtime-зависимость Aura. UI JS библиотека не заменяется; dataframe/CPU не следует добавлять в async request path. Потенциальный независимый oracle в отдельном research env; сейчас не подключать ради четырёх формул. Прямой numerical parity с пакетом НЕ запускался. |
| [polakowo/vectorbt](https://github.com/polakowo/vectorbt/tree/8e30b8ce102f302bec0c0226e05b59714453bebd) `8e30b8c` | **Apache 2.0 WITH Commons Clause**, GitHub SPDX NOASSERTION. Не считать обычной permissive Apache. Commons Clause ограничивает Sell, включая определённые платные услуги на основе функциональности. | Не архивирован, pushed 2026-10-23. Python>=3.11,<3.15; numpy>=2.4.6, pandas>=3.0.3,<4, numba>=0.66, scipy, matplotlib, plotly, sklearn, widgets и др.; full extras включают API-клиенты. | Конфликт с фиксированным numpy==2.2.6 Aura. Тяжёлая JIT/dataframe среда и лицензионный review для коммерческой интеграции; в FastAPI/production не включать. Возможен отдельный exploratory adapter после лицензирования и event-driven parity. Готовый Decimal Lab engine уже существует; см. BACKTEST_ARCHITECTURE.md. |
| [Mouses007/Crypto-Trading-Journal](https://github.com/Mouses007/Crypto-Trading-Journal/tree/a51d161a9a756bb001e9a32f95fbf2d314d8618a) `a51d161` | LICENSE GPLv3, package GPL-3.0-or-later. Successor AutarkTrade заявлен как AGPLv3. | README явно «no longer developed», перенесён в AutarkTrade. Vue3/Vite/Express, better-sqlite3/Knex/pg, LWC5.2.1, ws/axios; auto-update/exchange integrations. | Не drop-in к plain JS/FastAPI, другая БД/схема и авторизация. Даже совместимая major LWC не делает приложение совместимым целиком. Copyleft review нужен до заимствования/распространения кода; не копировать, не подключать автоматические updates/API/sync. Новый журнал Aura — самостоятельный local-only notebook. |

## Неоднозначность названий

Пользователь не указал URL OpenCharts и Crypto Trading Journal. Для OpenCharts
выбран современный финансовый `dylanpersonguy/OpenCharts`, а не старые проекты
визуализации/Sencha. Для Journal рассмотрен `Mouses007/Crypto-Trading-Journal`,
поскольку это приложение журналирования с Bitget/LWC. Дополнительно проверен
[Pa55w0rd/Crypto-Trading-Journal](https://github.com/Pa55w0rd/Crypto-Trading-Journal/tree/6cdbf417b3ad45fb04eb94d728794746fde0469e):
в snapshot нет лицензии и package manifest, это записи о торговле, а не пригодная
зависимость. Отсутствие лицензии НЕ разрешает копирование. Его код не использован.
Имена не доказывают, что пользователь имел в виду конкретный upstream.

## Что сохранено

Существующий vendored TradingView Lightweight Charts **5.0.8**, его Apache 2.0
LICENSE/NOTICE, атрибуция и ссылка на TradingView не изменены. Новая SVG-разметка
использует публичные coordinate/price/time APIs существующего chart instance;
нет копии сторонних drawing plugins. Формулы MACD/RSI и геометрия Фибоначчи
реализованы самостоятельно и проверены известными/независимыми вычислениями.

Для всех чужих библиотек dependency manifests не заменяют полный supply-chain
аудит. Поскольку ни одна не добавляется в runtime, lockfiles и действующие
зависимости Aura остаются неизменными. Нет утверждений об установочной,
нагрузочной или runtime-совместимости непроверенных upstream пакетов.

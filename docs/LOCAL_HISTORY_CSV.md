# Локальная история Binance CSV

В проект добавлен отдельный offline-источник для исследовательских данных:
`app/lab/local_csv.py`. Он не вызывает сеть, не импортирует Paper/Auto или
клиенты аккаунта и не меняет production HistoryService.

Импорт:

```bash
python -B scripts/import_binance_csv.py \
  BTCUSDT-15m-2026-09.csv \
  --month 2026-09 \
  --output /tmp/btcusdt-15m-2026-09.local.json
```

Команда принимает headerless CSV из Binance и CSV с первой строкой
`open_time,open,high,low,close,volume,...`. `open_time` и `close_time`
проверяются в миллисекундах или микросекундах. Проверяются OHLCV, закрытие
свечи, порядок, дубликаты и непрерывность 15m-интервалов. Пропуски не
заполняются. Нулевой объём допускается. Будущие и формирующиеся свечи
отвергаются по текущим UTC-часам. Заголовок и число колонок проверяются целиком:
поддерживаются 6 OHLCV колонок, 7 с close_time и полный Binance формат из 12
колонок. Все строки должны иметь одинаковую структуру. `--month 2026-09`
дополнительно требует точные границы сентября и 2880 непрерывных свечей.
Файл ограничен 16 MiB и 20 000 строками — это лимиты локального
исследовательского импорта, они не меняют лимиты публичного API.

Без `--start` сохраняется полный локальный диапазон и его SHA-256. Это raw
snapshot для последующей диагностики. Strategy Lab требует 250 четырёхчасовых
баров прогрева (4000 15m свечей), поэтому файл из 2880 сентябрьских свечей
сам по себе не может быть полным Strategy Lab snapshot. Импорт не создаёт
недостающие бары и не заявляет результат бэктеста. Для файла, который реально
содержит такой прогрев, можно запросить строгую форму:

```bash
python -B scripts/import_binance_csv.py FILE.csv --format lab --start UNIX_UTC_4H \
  --output /tmp/lab-snapshot.json
```

Если прогрева нет, команда возвращает `INSUFFICIENT_WARMUP`. Это намеренное
ограничение причинного анализа, а не ограничение числа строк CSV. Текущая
production Historical Pattern диагностика имеет отдельное требование минимум
500 баров контекста. Для её существующего загрузчика добавлен отдельный формат:

```bash
python -B scripts/import_binance_csv.py BTCUSDT-15m-2026-09.csv \
  --format diagnostic --month 2026-09 \
  --output /tmp/btc-september-diagnostic.json
```

Этот формат содержит numeric Candle для production-кода и Decimal-строки
оригинальных OHLCV для контроля преобразования. CSV не считается независимо
подтверждённой историей Binance: сохраняется SHA-256 именно прочитанных байтов
и пометка о заявленном пользователем происхождении. Hash обеспечивает
воспроизводимость, но не доказывает подлинность.

Если есть только сентябрь, первые 500 свечей можно использовать как реальную
историю прогрева: тогда диагностировать можно оставшиеся 2380 свечей, а не
заявлять полный 30-дневный результат. `load_snapshot(path, start, end, warmup)`
и `replay(candles, start, end)` из `scripts/diagnose_aura_auto.py` уже принимают
такой диапазон. Existing CLI бэктеста 30/90 дней продолжает требовать весь
запрошенный диапазон плюс прогрев: этот импорт не ослабляет его проверки.

Для полного сентября нужно добавить реальные предыдущие бары: минимум 500
для production-диагностики; production live archive обычно содержит 10 000,
поэтому 500 не воспроизводят весь набор аналогов live. Strategy Lab требует
4000 перед началом общего диапазона. Стратегия и пороги не изменяются.

## Аудит архитектуры и ограничений

| Компонент | Назначение / ограничение |
| --- | --- |
| `app/providers.py`, `app/live.py`, `app/market_state.py` | Публичные REST/WebSocket и live-окно; не изменены |
| `app/patterns/history.py` | Production HistoryService, SQLite-архив и кэш; локальный импорт в них не пишет |
| `app/patterns/{engine,backtesting}.py` | Production Historical Pattern и native replay; формулы не изменены |
| `app/lab/data.py` | Research Loader, общий snapshot, strict restore; публичная пагинация сохранена |
| `app/lab/experiment.py` | Existing research backtester; `--format lab` проверяется его restore-контрактом |
| `scripts/{diagnose_aura_auto,backtest_aura_history}.py` | Изолированные production Paper replay и отчёты; loader совместимость проверена |
| `app/paper/`, account clients | Persisted ledger и read-only аккаунты; CSV importer от них изолирован |

2000 — размер live/UI окна, не предел существующего исторического архива.
CSV импорт допускает 20 000 строк, API страницы Binance остаются ≤1000;
Strategy Lab snapshot остаётся ≤12 000 базовых баров, включая прогрев.
Ограничение native Pattern backtest — максимум 100 решений за запрос, а не
100 свечей истории. Долгие production replay следует выполнять отдельно от
Render worker; UI, лимиты API/памяти/CPU и защита аккаунта не расширены.

Все 2880 свечей импортируются и доступны для анализа OHLCV/индикаторов.
Оценка торговых решений с прогревом исключает начальные свечи из тестового
результата либо требует предыдущую реальную историю. Доходность не оценивалась.

Файл не загружается в Render и не выбирается live API: он передаётся в
исследовательский CLI явно. Реальный `BTCUSDT-15m-2026-09.csv` в среде Codex
не считается проверенным, пока файл не присутствует по указанному пути.

## Выполненные проверки

В текущей среде исходного CSV нет. 2880 сентябрьских строк проверялись
исключительно на синтетической unit-test фикстуре; результаты стратегии и
доходность на ней не оценивались.

- 24 CSV regression tests: PASS. Включают ms/us, 12 колонок, нулевой объём,
  malformed headers/numbers, duplicates/gaps, future/forming, resource limits,
  полный месяц, existing diagnostic loader и actual Lab execution compatibility.
- Полный Python suite: **716 passed**, одна существующая Starlette deprecation warning.
- Node: **101 passed** (57 Paper, 9 market reliability, 13 Bybit, 11 Binance, 11 Lab).
- Python AST syntax, app imports, JS syntax, heuristic credential scan и
  exchange-write/private-client dependency scan: PASS.
- Frontend build отсутствует по архитектуре (обычный HTML/JS); browser/Render/mobile
  live test и импорт реального CSV: NOT RUN.

В Cloud полный pytest запускался временным `/tmp/run-aura-tests.py` с event-loop
workaround в тестовом процессе и `PYTHONPATH=/tmp/aura-test-deps:<repository>`;
production event loop не изменялся. Проверены установленные FastAPI 0.141.1,
uvicorn 0.52.1, httpx 0.28.1, websockets 16.0, NumPy 2.3.5; точное окружение
requirements.txt не переустанавливалось и не заявляется проверенным.

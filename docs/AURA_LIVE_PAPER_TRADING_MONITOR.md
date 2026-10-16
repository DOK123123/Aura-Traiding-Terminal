# AURA 4.2 — LIVE PAPER TRADING MONITOR

## Текущий вывод

**WAITING_FOR_REAL_SIGNAL** — реальный production OPEN → CLOSE этой сессией
не подтверждён. Это не заявление об отсутствии сделок на сервере: у рабочей
среды нет owner-доступа к Render/Supabase, а публичный web-reader не смог
прочитать даже health endpoint. Публичная недоступность для инструмента не
доказывает неисправность Render. Пользовательские ONLINE/CONNECTED сведения
не заменяют проверку связанной цепочки сохранённых событий.

Изменения подготовлены на main `1a39aa4c00cf9067a2c87bb33c7eb25e0391dff1`.
Production deploy, tick/control, изменения баланса/позиций и SQL не выполнялись.
Не нужно отправлять агенту пароли или service-role keys. После deployment
владелец может прочитать доказательство через новую защищённую панель.

## Production-путь

1. Внешний scheduler вызывает прежний защищённый POST `/api/auto42/tick`.
   Секрет scheduler независим от owner-auth; браузер не вызывает tick.
2. `Service.snapshot` → `snapshot_for_auto` → production MarketContext:
   закрытые BTCUSDT 15m свечи Binance Spot, прежняя source/freshness/hash проверка.
3. Прежняя `strategy` определяет подтверждённый setup. Параметры, ADX,
   alignment, volatility/structure/liquidity-фильтры не менялись.
4. `engine.advance` записывает pending signal, затем при обработке следующей
   закрытой свечи `open_virtual` применяет прежние mode/emergency, freshness,
   daily-loss/drawdown, позиционные, notional, balance и fee-inclusive risk gates.
   Execution model остаётся **CLOSED_SIGNAL_NEXT_OPEN**: виртуальная цена входа
   берётся из open следующего бара, а запись делается после его закрытия.
   Поэтому effective entry_time и время записи scheduler события различаются.
5. Прежний CAS `store.commit` атомарно сохраняет account, watermark, pending,
   позиции, бухгалтерию и события в Supabase. Нет отдельного trading engine.
6. Следующие tick проходят через прежние `protective` и `mark`.
   STOP/TP, adverse gaps и ambiguous SL/TP разрешаются существующим движком.
7. `close_virtual` рассчитывает прежние exit fee, slippage, realized PnL,
   balance/equity и trade counters. CLOSE и состояние сохраняются тем же CAS.

`engine.py`, `strategy.py`, market data, indicators, risk policy, SQL schema,
storage transport, scheduler script/workflows/Cloudflare worker, exchange source
и пакет аналогов в этом изменении не редактировались. Bitget/BingX сохранены.

## Наблюдение поверх существующего исполнения

`app/automated/live_monitor.py:observe_tick` получает уже вычисленные
state/events **после** `advance`. Он не вызывает strategy, mark, protective,
open/close или exchange client и не меняет финансовые поля. Добавляет только
`state.live_paper_monitor` и append-only события `kind=LIVE_MONITOR` в уже
существующую таблицу событий; semantic event type находится в payload.
Первичные OPEN/CLOSE/DECISION/REJECT/TICK записи сохраняются без изменения.

| Event type | Источник |
|---|---|
| SIGNAL | Реальное направление из production strategy в DECISION |
| REJECTED | DECISION без постановки входа либо прежний execution REJECT |
| OPEN | Прежнее событие OPEN после risk gates |
| POSITION_UPDATE | Новый сохранённый closed-candle liquidation mark позиции |
| CLOSE_TP | CLOSE с TAKE_PROFIT / conservative gap reason |
| CLOSE_SL | CLOSE со STOP_LOSS / ambiguous / gap reason |
| ERROR | Ошибка данных/контроллера, дошедшая до сохраняемой транзакции |

Каждая запись содержит UTC epoch timestamp, position_id (null, если позиции
ещё нет), scheduler_run_id, closed_candle_at, candle_id, reason, source,
origin Render/backend/commit/controller-instance. ID run — прежний атомарный
tick operation key; ID candle явно обозначает **close**.
SIGNAL position_id — будущий candidate ID, а не доказательство открытия.
В ERROR candle_role=LAST_PROCESSED и attempted_closed_at различают последнюю
известную свечу и неудавшуюся попытку; неизвестные данные не выдумываются.

Summary хранит только последние signal/rejection/open/update/close/error и одну
подтверждённую цепочку; история остаётся append-only в events, не растёт внутри
account payload. Повторный tick/CAS retry не создаёт повторного открытия или
дублирующих monitor records. Для legacy position/pending не создаются
искусственные исторические SIGNAL/OPEN. Требуется новая полностью наблюдённая
цепочка после deployment.

Monitor работает на копиях; исключение при его сборке не отменяет расчёт
исходного исполнения/защитного выхода. Ошибка monitor показывается как FAILED.
Реальная ошибка commit по-прежнему отклоняет всю транзакцию. При недоступном
storage невозможно честно записать в него ERROR; last write error текущего
процесса и endpoint FAILED показывают это без фиктивного persisted event.
RPC load, как и существующий status, способен инициализировать OFF-account,
если account отсутствует; существующий production account не сбрасывается.

## Панель и API

Owner-only **LIVE PAPER TRADING MONITOR** на существующей странице.

- GET `/api/auto42/live-monitor`: подтверждённо прочитанное состояние, checksum,
  revision/last_saved_at, последнее ограниченное окно journal и technical evidence.
- GET `/api/auto42/live-monitor/events?after=0&limit=100`: курсорный журнал.
  next_cursor двигается по всем исходным событиям; пустой semantic page может
  содержать ещё legacy строки. Повторять с next_cursor, пока больше нет данных.
  Максимум 200 исходных строк за запрос. История может содержать разные epochs;
  основной dashboard ограничен текущим epoch.
- Существующие owner-auth и no-store обязательны. Параметры не выбирают
  произвольный файл, базу, URL или account. Новых mutation endpoints нет.

Панель показывает tick/processed candle, последний сигнал и отказ, позицию,
effective entry time/price/SL/TP, closed-candle net liquidation PnL с обеими
комиссиями, последний CLOSE с reason/time/fees/PnL, balance/equity и storage
revision. Свежий PnL скрывается при старом mark/tick или data error; последний
известный mark явно обозначен. Это не streaming tick PnL.

Polling раз в 30 секунд только при открытой видимой панели; закрытый браузер
останавливает чтение, а не внешний scheduler. GET не запускает tick, settlement,
тест, market fetch или запись. Live browser-absence/restart не утверждаются
по одному факту записи OPEN/CLOSE: отдельные поля остаются NOT_OBSERVED.

## Правила статуса

**VERIFIED** требует внутри прочитанного durable Supabase account:

- связанную SIGNAL → OPEN → CLOSE_TP/CLOSE_SL цепочку с одним position_id;
- OPEN/CLOSE, записанные серверным tick, а не replay/test output;
- Render provenance и допустимый deployment commit для открытия/закрытия;
- отсутствие текущей data/storage/monitor ошибки для верхнего VERIFIED status.

Цепочка хранится в checksum-protected account и journal, переживает restart и
вытеснение старых записей из 200-row окна. Верификация ограничена наблюдённым
виртуальным циклом. Она не доказывает будущую доступность или прибыльность.

**WAITING_FOR_REAL_SIGNAL**: полной подходящей цепочки пока нет. reason
различает отсутствие цепочки, pending next-open и ожидание CLOSE.
Это также статус локального SQLite теста: он никогда не доказывает production.

**FAILED**: текущая data/storage/monitor error или невозможность прочитать
состояние. Уже сохранённое прошлое доказательство не превращается в доказательство
текущей работоспособности. Health/ON/CONNECTED/trade counters/Replay PASS сами
по себе не устанавливают VERIFIED.

## Изолированный технический OPEN → CLOSE

`scripts/verify_live_paper_monitor.py` использует существующий production
Service/SQLite/engine и синтетический TestMarket **только** во временном каталоге.
`configured()` и production clients не вызываются. Сначала выполняются прежние
5 LONG/SHORT TP/SL/ambiguous сценариев с независимым Decimal accounting oracle,
restart/concurrency и safety controls. Затем отдельный trace проверяет настоящий
controller SIGNAL/OPEN/POSITION_UPDATE/CLOSE в изолированном SQLite account.

`docs/AURA_LIVE_PAPER_TECHNICAL_VERIFICATION.json` — code-hash/checksum-bound
**TEST ONLY**, `proves_live_autonomy=false`, live Supabase/Render NOT_TESTED.
GET только читает этот статический файл. Изменение кода или файла делает
старое доказательство NOT_TESTED; endpoint не запускает тестовые сделки.

```bash
python -m scripts.verify_live_paper_monitor --output /tmp/technical-only.json
python -m pytest -q
node tests/test_live_paper_monitor_frontend.cjs
```

Для текущей cloud-среды технический runner поддерживает `--sandbox-poll`;
полный pytest использует существующий диагностический helper:

```bash
python -B - <<'PY'
from scripts.replay_aura_csv import enable_sandbox_poll
enable_sandbox_poll()
import pytest
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider','--tb=short']))
PY
```

## Выполненные проверки и review

- Полный Python suite: **1198 passed**, одно upstream Starlette/AnyIO
  DeprecationWarning; 109.03 секунды.
- Все **16 JavaScript/Node test suites PASS**.
- Синтаксис всех Python файлов, import app.main, node --check нового JS и
  diff whitespace check для нового изменения: PASS.
- Повторное сравнение старого production execution runner на main-tree и новом
  коде: все возвращаемые результаты пяти сценариев полностью идентичны,
  включая balance/PnL/fees/slippage, restart и duplicate protection.
- Изолированный monitor trace: OPEN=1, CLOSE=1, POSITION_UPDATE присутствует;
  restart восстановлен, повторного входа нет, status WAITING_FOR_REAL_SIGNAL,
  live_cycle_verified=false. Технические деньги не относятся к owner account.
- Новые тесты: owner auth/no-store, journal cursor bounds, stale/error,
  failed commit без частичных записей, capture exception без блокировки
  обычного открытия, restart/SL, дубли/конкуренция, stale PnL masking,
  совпадение net liquidation PnL с существующей equity, legacy evidence
  без ложного VERIFIED. Положительный тест Render/Supabase predicate использует
  **симуляцию над временным SQLite**, не реальные production данные.

Code review: только пассивная сборка после existing settlement и перед тем же
CAS commit; финансовые поля и первичные events не меняются. Scope review:
strategy/engine/storage/SQL/scheduler/source/analogs byte-for-byte unchanged.
Security review: owner-only GET, no-store, bounded read/cursor/output, no HTML
injection, никаких credentials в journal или artifact; код тестов не вызывается
из HTTP. Блокирующих high/critical findings в проверенном diff не найдено.
Live Supabase/Render restart и live browser-absence: NOT_OBSERVED.
Новый deployment и реальный autonomous OPEN/CLOSE: NOT_VERIFIED.

## Проверка на Render после одобрения

1. Проверить Draft PR и разрешить интеграцию/deploy отдельно. Автор этой
   сессии не выполняет merge/deploy. Сохранить выбранный SHA.
2. Deploy разрешённого коммита существующим Render workflow. Не менять
   Environment Variables, Binance source, scheduler частоту/offset или SQL.
   Не запускать RESET/START/tick вручную ради появления сделки.
3. Войти существующим owner способом и открыть монитор. До новой полной цепочки
   ожидается WAITING_FOR_REAL_SIGNAL. Проверить tick, processed candle,
   отсутствие last_error, SUPABASE_POSTGRES/durable, checksum/revision/save time.
4. Закрыть браузер на несколько обычных scheduler интервалов, затем открыть
   панель: время tick/run IDs должны продолжать двигаться. Сохранить read-only
   JSON; не считать только открытый браузер доказательством автономности.
5. Дождаться **естественного** валидного сигнала. Зафиксировать SIGNAL и тот
   же position_id в OPEN, risk_usdt≤risk_budget, effective entry/SL/TP,
   persisted revision и комиссии. Не ослаблять стратегию для ускорения.
6. Во время позиции наблюдать POSITION_UPDATE. Для live restart проверки нужен
   отдельно согласованный обычный restart Render; эта сессия его не выполняет.
   После restart проверить сохранённые position ID/size/SL/TP и отсутствие
   второго OPEN. Новый controller_instance сам по себе не доказывает restart:
   это может быть другой worker.
7. Дождаться естественного SL/TP. Проверить CLOSE_TP/CLOSE_SL с тем же ID,
   exit time/price, entry+exit fees, realized PnL и изменение balance по прежнему
   accounting. Перечитать состояние после закрытия для подтверждения сохранения.
8. Только после подходящей цепочки монитор может выдать VERIFIED. Если цепочки
   нет — сохранить WAITING_FOR_REAL_SIGNAL. При FAILED сохранить точный code
   и run/candle IDs, не обходить риск или freshness guards.

Владелец может экспортировать JSON, не включая cookies, Authorization headers,
пароли, scheduler secret или service-role keys. Для внешней проверки нужны
события/IDs/SHA/revisions, а не credentials.

# Aura 4.2 — исправление лишней вычислительной работы MarketContext

База main: 47c6c9e5aa1f2c36fdef3fc4006650789346e0eb. 15 октября 2026.

## Что установлено

START ждёт MarketContext перед записью ON. При ANALYSIS_TIMEOUT состояние OFF
правильно сохраняется. Supabase не должен получать ON при неуспешном preflight.
Предыдущий commit исправлял лишь преждевременный timeout ожидающего shared task;
он не ускорял сам расчёт. В этой задаче deadlines не повышались.

Воспроизводимый CPU profile полного окна 4175 свечей обнаружил горячий участок:
research/market_intelligence/structure.py:zones. Original analyze_window под
cProfile: 1.850 s cumulative; segment_states 1.774 s, zones 1.105 s (~60%).
7735320 вызовов, в том числе 4138004 вызова генератора пересуммирования кластера.
Это fixture-профиль рабочей среды, не измерение Render и не торговый backtest.

Причина лишней работы: на каждой исторической свече (15m/1h/4h) зоны строятся
заново; для каждого следующего pivot исходный zones повторно суммирует весь
растущий кластер, хотя порядок/содержимое его предыдущего prefix не меняется.
Для плотного кластера 32 pivots: 32 вызова sum, включая финальную сумму.
Оптимизированный вариант — один sum при создании и затем одно Decimal-сложение
на каждый добавленный pivot. Сортировка, предел 32, tolerance, округление,
порядок сложений, touches и confirmation time сохранены.

Это доказанный вычислительный дефект и его исправление. Что именно ограничивает
конкретный процесс Render (compute deadline, ожидание общего task, CPU contention,
другая задержка) всё ещё требует его авторизованной диагностики. Нельзя объявлять
этот локальный профиль доказательством production root cause или успешного ON.

## Результат измерения

Один и тот же fixture(4175), analyze_window, три прогона, без cProfile:

| Вариант | Секунды | Медиана |
|---|---|---|
| Original zones | 0.7316, 0.7506, 0.7131 | 0.7316 |
| Optimized zones | 0.4141, 0.3869, 0.4236 | 0.4141 |

Сокращение median runtime ~43.4%, ускорение ~1.77x. Это не SLA и не обещание
таких же времен на Render Free. Deadline COMPUTE_SECONDS=8 остался прежним;
сетевые и START/tick бюджеты также не менялись.

## Точность и причинность

Регрессии сравнивают zones с буквальной предыдущей реализацией на Decimal
precision 8/16/28/50, разных размерах входа, tolerance и кластеризации.
Дополнительно полные market states на 15m/1h/4h сравниваются по canonical digest
с тем же segment_states и подставленной reference zones: точное совпадение.
Количество prefix sum проверяется независимо от wall-clock timing: 32 → 1.
Нет новых наблюдений, future pivots, другой глубины истории или новых сигналов.

## Почему изменён runtime artifact

Shipped analogs-v4.json.gz строго хранит SHA256 исходных файлов. Performance-only
изменение structure.py закономерно делает старую source signature несовместимой.
Loader/checks не ослаблялись. Вместо переиндексации истории обновлено только
поле software для одного файла и зависимый content checksum. Сами данные,
4136 states, outcomes, normalizers, источники и их даты неизменны.

Воспроизводимый scripts/rebind_analog_software.py разрешает только известный
исходный архив и конкретный переход SHA256 structure.py. Любой другой input,
любое другое изменение software или payload отклоняются. Затем применяется
исходный строгий AnalogIndex validator. Нет автоматического runtime rebind.

- Original structure SHA256: 984295140de91d696e6b693c2a54124ce8f02f169c71325aa9deef2deffacfe6
- New structure SHA256: 9fd64bab64c49409f8a5c6893ab5d822cf8782783e01e17f07f79917f30ca1d3
- Original artifact SHA256: e4db02f80f47d8b5071af987957106e0d560a5bf77d32db9af3cfde50ba9e82d
- New artifact SHA256: 05a669e562f78db1453dc57d88206287a03e00d0ebdf9916a667e840e6f96fa6
- Payload excluding software/content checksum (unchanged): bea47e3768d366a456faed70ee039cc3a0e16407eacc5ea9ac923eb3f6e6e837

Предыдущие исследовательские отчёты остаются неизменными и ссылаются на свой
исторический artifact. Новая runtime source signature может создать новый
Forward Validation cohort; старые записи не переписываются. Финансовый policy
hash Auto42 не меняется; RESET или миграция портфеля не требуется.

## Реальные данные и production

Из рабочей среды выполнен настоящий публичный Binance Spot запрос:
4168 закрытых 15m свечей, полный snapshot+анализ+стратегия за 3.331 s.
checked_at=1792087264, last_closed_at=expected_closed_at=1792087200,
status=OK, decision=MTF_NOT_ALIGNED, source=data-api.binance.vision.
Это не запрос из Render. Сделок/портфелей/ключей в этой проверке нет.

Авторизованный START в production не выполнялся: агенту не предоставлен доступ
owner session/Render environment. Предыдущие ошибки пользователя после deploy
приняты как наблюдение пользователя; точный SHA backend не угадан по сообщению.
Production ON после этого commit НЕ ПОДТВЕРЖДЁН.

## Применение

Развернуть новый main на Render. Не менять risk/strategy, не делать RESET.
При последующем явном START владельца требуются fresh validated candles и все
исходные проверки. Если timeout остаётся, статус остаётся OFF и diagnostics.market
покажет ANALYSIS_COMPUTE либо ANALYSIS_WAIT/UNCLASSIFIED, source и timestamps.
Сам факт локального ускорения не разрешает запуск без свежих данных.

Команды:

```sh
python -m pytest -q
for file in tests/*.cjs; do node "$file" || exit 1; done
python -m pytest -q tests/test_market_zones_performance.py
```

Rebind воспроизводится на исходном pack из parent commit, не на уже изменённом:

```sh
python -m scripts.rebind_analog_software ORIGINAL_analogs-v4.json.gz NEW_analogs-v4.json.gz
```

Benchmark: fixture из tests.test_market_context; analyze_window на одинаковом
окне, monkeypatch structure.zones=tests.test_market_zones_performance.reference
для original, без patch для optimized, три time.perf_counter прогона. Только для
benchmark использовался COMPUTE_SECONDS=120, чтобы профилирование не обрывалось;
это тестовый monkeypatch, не production настройка или изменение дедлайна.

## Итог проверок

- Финальный полный Python suite: **1127 passed**, 0 failed, 1 Starlette/AnyIO
  deprecation warning, 68.26 s.
- Все 11 JavaScript suites: **167 passed**, 0 failed.
- Python AST и штатная загрузка AnalogIndex: PASS; реальный публичный snapshot
  также подтвердил загрузку rebased artifact без отключения проверок.
- Дополнительный test counts sum calls: 32 original / 1 optimized, одинаковый
  точный output. Нет нестабильного требования «успеть за X ms» в unit tests.
- Code/security review: Decimal order preserved, no future inputs, all deadlines
  unchanged, no new network/private clients, strict artifact checks unchanged.
- Production: GET /api/health HTTP200; GET /api/auto42/status без авторизации
  HTTP401. Авторизованные START, Supabase mode=ON, restart Render и Cloudflare
  runtime: NOT RUN. Новая версия на Render агентом не развёртывалась.

Файлы: research/market_intelligence/structure.py;
scripts/rebind_analog_software.py; tests/test_market_zones_performance.py;
app/intelligence/data/analogs-v4.json.gz; docs/AURA_AUTO42_COMPUTE_PERFORMANCE.md.

Cloud tests: PYTHONPATH=/workspace/ecc-audit-deps:$PWD,
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, python -B, enable_sandbox_poll() из
scripts/replay_aura_csv.py, pytest.main(['-q','-p','no:cacheprovider','--tb=short']).
Production event loop не менялся. Новых зависимостей нет.

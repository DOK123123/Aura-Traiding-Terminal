# ECC-аудит Aura: фактические проверки

Дата: 14 октября 2026, Europe/Moscow. Все торговые проверки offline,
с временными SQLite и dummy credentials. Биржевые запросы мокированы;
тесты не отправляют ордера. `requirements.txt` не менялся.

## Окружение

Проектные зависимости установлены в `/workspace/ecc-audit-deps` отдельно
от глобального Python, только wheel packages из обычного pip source:

```bash
python -m pip install --target /workspace/ecc-audit-deps --only-binary=:all: \
  --no-compile --disable-pip-version-check --no-input --timeout 5 --retries 0 \
  -r requirements.txt
```

Python 3.12.14; Node 24.19.0. Тестируемые pins: FastAPI 0.115.12,
uvicorn 0.34.2, httpx 0.28.1, pytest 8.3.5, websockets 15.0.1,
numpy 2.2.6. Полученные transitives: Starlette 0.46.2,
Pydantic 2.14.1, AnyIO 4.15.1; они записаны в evidence JSON.

Глобальная среда имеет другие версии FastAPI/Starlette/uvicorn/numpy/websockets.
Pip сообщил конфликт с глобальным `sse-starlette`; Aura его не использует,
глобальные пакеты не изменены. Тесты запускаются с target-directory PYTHONPATH.
Эти результаты не доказывают, какие версии сейчас установлены на Render.
Полного lockfile всех transitive dependencies пока нет.

## Результаты

| Проверка | Статус | Фактический результат |
| --- | --- | --- |
| Authentic baseline vs GitHub | PASS | 229/229 Git blob hashes совпали с `68a33a32...`; .git локально отсутствует |
| Baseline полный pytest | PASS | **907**, 0 failures/errors/skips |
| Итоговый полный pytest | PASS | **970**, 0 failures/errors/skips, одна dependency deprecation warning |
| Независимый повтор полного pytest | PASS | **970**, 0 failures/errors/skips |
| Отдельный unittest discovery | PASS | **193**, 0 failures/errors/skips; входит в pytest, числа не суммируются |
| JavaScript | PASS | **127** уникальных cases, 8 suites, 0 failures/skips |
| Новые Python regressions | PASS | 62 cases в новых Python файлах + 1 выделенный legacy regression: прирост 63 к baseline |
| New Replay JS | PASS | 11 stateful cases; прирост к baseline 116 JS |
| Python syntax/import | PASS | 131 project Python files AST; `import app.main` |
| JS syntax | PASS | Все static JS, включая vendor, и Node test files `node --check` |
| ASGI/API/auth | PASS | Owner 401/403, CSRF, protected GET, Replay confirmation, unconfigured accounts, health/static |
| Trading/accounting/causality | PASS | LONG/SHORT, costs, opening SL/gaps/ambiguity, risk, calendar, restart, duplicate execution |
| Дополнительные static HTML GET/HEAD | PASS | 22 normalized-path probes; успешные HTML ответы защищены от framing |
| Custom static secret scan | PASS в указанном scope | Высокоспецифичные PEM/token/access-key patterns не найдены; дополнительно просмотрен intended diff. Не гарантия отсутствия любого возможного секрета |
| Private exchange write/import scan | PASS | Нет добавленных writes; fixed Testnet/Demo GET allowlists, auth/risk models неизменны |
| Mocked hosting entrypoint | PASS | `app.main:app`, host 0.0.0.0, env PORT, worker1; валидные/невалидные PORT проверены без сервера |
| Ruff/mypy/pyright/bandit | NOT RUN | Не доступны в финальном test environment; результаты не выдуманы |
| Coverage | NOT RUN | Процент не измерен; 80% не заявляется |
| Dependency vulnerability database / pip-audit | NOT RUN | Статический dependency/version review выполнен; автоматический advisory scan не завершён |
| npm build/audit / TypeScript | Не применимо | Plain JS, package.json/frontend build отсутствуют |
| Real Chromium/Android | NOT RUN | Playwright package есть, Chromium/headless-shell binary отсутствует; browser launch не состоялся |
| Live Binance/Bybit/Testnet/Render | NOT RUN в этом аудите | Нет реальных credentialed requests, live orders, deploy или Render config изменений |

Отчёт независимого reviewer и компактное evidence — в `docs/ecc/`.
Большие исходные archives, полные journals, dependency target и SQLite не в git.

## Не скрытые ошибки промежуточных проверок

Отдельный ранний Testnet logger regression действительно воспроизвёл leak
**dummy** key/secret через поздний child logger. Полный baseline suite при
другом порядке тестов проходил: это не опровергает самостоятельное воспроизведение.
Добавлены независимые handler/fallback/cleanup проверки, они проходят.

Первый интегрированный исправленный suite дал 967 PASS / 1 FAIL из-за ошибочного
нового assertion названия Paper UI; fixture исправлена без изменения runtime.
Позднее независимый прогон дал 969 PASS / 1 FAIL из-за предположения только
`application/javascript`; текущий MIME registry законно возвращает
`text/javascript`. Assertion принимает оба стандартных типа, сохраняя status200
и все HTML/header проверки. Затем полный suite и независимый повтор: 970 PASS.

Старый тест ожидал, что подтверждённая коррекция свечи автоматически исчезнет.
Он разделён на latch regression и отдельный out-of-order/gap/manual-gap-close
тест. Это исправление доказанного safety expectation, не отключение теста.
Ни один case не deselected/skipped в итоговом полном suite.

## Воспроизводимый запуск

Cloud polling workaround применяется **только в test runner**, production
loop/app не меняются:

```bash
PYTHONPATH=/workspace/ecc-audit-deps:$PWD PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -B - <<'PY'
from scripts.replay_aura_csv import enable_sandbox_poll
enable_sandbox_poll()
import pytest
raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider', '--tb=short']))
PY

PYTHONPATH=/workspace/ecc-audit-deps:$PWD \
PAPER_DB_PATH=/tmp/aura-ecc-disposable-paper.sqlite3 python -B - <<'PY'
import unittest
from scripts.replay_aura_csv import enable_sandbox_poll
enable_sandbox_poll()
r = unittest.TextTestRunner().run(unittest.defaultTestLoader.discover('tests', pattern='test_*.py'))
raise SystemExit(not r.wasSuccessful())
PY

for f in tests/*.cjs; do node "$f" || exit 1; done
```

За пределами этой sandbox обычно достаточно `python -m pytest -q` после
установки requirements. ASGI/VM tests не заменяют реальный browser/device test.

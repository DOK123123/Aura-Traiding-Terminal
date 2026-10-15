# Aura 4.2: сдвиг расписания GitHub Actions

Дата: 15 октября 2026. База: f698f72eda84d4509e66a1f5d7c431997a37351b.

## Наблюдения до изменения

GitHub API: workflow 384851371 active; main — основная ветка. История содержит
12 запусков, из них только 3 schedule: #1/#2 skipped, #8 failure. #11/#12 —
успешные workflow_dispatch. Новых schedule после #8 (09:27:22 UTC) при повторной
проверке не обнаружено. Это не доказательство полного отключения расписания.

Текущий cron синтаксически корректен. Условие virtual_tick:
`vars.AURA_AUTO42_ENABLED == 'true'`. Выполнение job #11/#12 подтверждает прохождение
условия в эти моменты. Прямой доступ к текущим Variables/административным настройкам
Actions недоступен через connector. Старые skipped jobs согласуются с непройденным
условием; точное прежнее значение переменной неизвестно.

Отсутствие новых событий schedule нельзя объяснить сном Render: HTTP к Render
происходит после создания job. Причина редкой доставки событий на стороне GitHub
не доказана. GitHub официально допускает задержки/отбрасывание schedule при нагрузке,
особенно в начале часа. На предыдущей проверке GitHub Status: Actions operational.

## Минимальное изменение

`.github/workflows/aura-auto42.yml`: `*/5 * * * *` заменён на `2-59/5 * * * *`.
UTC минуты: 02,07,12,17,22,27,32,37,42,47,52,57. Интервал, включая переход часа,
пять минут. Это разрешённая владельцем мера снижения риска пиковых задержек,
а не доказанное исправление внутренней проблемы GitHub.

Не изменены gate, токены, секреты, concurrency, retries, риск, стратегия,
БД, портфель или START PAPER. Workflow_dispatch сохранён. Новые запуски агент
не вызывал. Автоматическая доставка после push пока не подтверждена.

## Проверки

- YAML разобран PyYAML BaseLoader; проверены schedule, workflow_dispatch,
  условие virtual_tick и cancel-in-progress=false.
- Проверена последовательность 12 минут и интервал через границу часа.
- 87 Python tests passed: test_auto42_scheduler.py, test_auto42.py,
  test_auto42_diagnostics.py, test_auto42_connection_evidence.py.
- 15 JavaScript tests passed: node tests/test_auto42_frontend.cjs.
- Полный suite повторно не запускался: runtime-код не изменялся.
- actionlint не запускался. Проверка YAML не равнозначна выполнению GitHub scheduler.
- Python: установленное тестовое окружение /workspace/ecc-audit-deps,
  enable_sandbox_poll(), pytest -q -p no:cacheprovider; production не менялся.

## Как проверить

1. GitHub Actions → Aura 4.2 virtual-only scheduler → фильтр Event: schedule.
   Оставить Auto Paper OFF. Ручной Run workflow не проверяет cron.
2. Наблюдать 1–2 часа, затем сутки. Ожидаются новые schedule runs на новом main;
   фактическое время может отставать от :02/:07/... .
3. У job virtual_tick должны быть исполненные шаги, а не skipped.
   При OFF ожидается HEARTBEAT_OFF, processed=False, opened=0, state_saved=true
   проверяется scheduler-клиентом. При открытой позиции защитное сопровождение
   может продолжаться; никаких reset для проверки.
4. Сопоставить время job с последним подтверждённым запуском/сохранением в Aura.
   Считать число запусков и максимальный разрыв, не только зелёный badge.
5. Если новых schedule нет через 30–60 минут, это контрольный порог наблюдения,
   не SLA GitHub: проверить Actions Variables, state=active и обратиться в GitHub
   Support с workflow ID и run IDs. Не объявлять режим работающим 24/7.
6. При устойчивых задержках рассматривать отдельный внешний scheduler с секретным
   header и уведомлениями после самостоятельной проверки. Не обходить авторизацию.

Deploy Render для cron не требуется: расписание читается GitHub из main.
Настроенный Auto-Deploy Render может независимо сработать на push; агент deploy
не запрашивал. Бесплатные GitHub Actions/Render не гарантируют строгую
пятиминутную доставку или непрерывную работу 24/7.

Источник: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

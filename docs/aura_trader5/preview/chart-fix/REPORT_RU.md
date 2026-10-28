# Исправление пустого графика Preview

## Причина

`app/manual_preview/page.py` обрезал исходную страницу перед scenario-journal вместе с исходным footer. Обязательный элемент `last-updated` исчезал. `clearData()` в `app.js` выбрасывал `TypeError: Cannot set properties of null (setting 'textContent')`; после успешного REST тот же отсутствующий элемент ломал отрисовку. Исключение обратного вызова `onData` попадало в обработчик ошибки `Hub.connect()`, запускавший STALE/reconnect и повторную загрузку истории. В Chromium desktop/Pixel 7 воспроизведены 201 валидная свеча в Hub, пустой счётчик и закрывающий график overlay.

Вторая проблема: `app.js` исполнялся до `manual-live-analysis.js`/`manual-live-feed.js`; начальная независимая загрузка истории возвращалась без запроса. Отдельная ошибка CI — fixture прибавляла 25 секунд ко всем candle timestamps, нарушая UTC alignment.

## Изменения

Preview сохраняет footer DOM target и загружает parser до chart bootstrap. UTC fixture исправлена; добавлено отрицательное утверждение для некратных timestamps. Серверные проверки истории не ослаблялись. График сохраняет историю при reconnect; ошибки имеют безопасный диагностический код в UI/console. Счётчик обновлений отражает принятые валидированные WS-сообщения.

## Проверка

- `node scripts/verify_manual_preview_chart.cjs work/chart-check`: Chromium desktop + Pixel 7 PASS; все 5 таймфреймов, 200 закрытых/201 с формирующейся свечой, EMA20/50, обновление close, обрыв WS и восстановление. Ноль JS exceptions, ноль POST.
- Это **локальный replay** публичного ответа Bitget, полученного 28 октября 2026, и контролируемых WS events. Это не доказательство доступности WS на Render или физическом Android.
- `tests/test_manual_preview.py` проверяет DOM contract и порядок скриптов на фактически генерируемой Preview HTML. `tests/test_manual_live.cjs` проверяет записанный реальный REST-формат и отклонение неверных timestamps.
- До исправления protected Preview возвращал 401 без owner Basic Auth. Cloud environment не содержит owner credential; конечная проверка защищённого развернутого графика требует этого доступа. Аутентификация не обходилась.
- Точный итог полного CI, commit и deploy будет указан в итоговом комментарии PR #62.

Код/security review: исправление ограничено DOM/графиком и тестами; стратегия, формулы, auth, SQL, настройки торговли, main/production/Active43/PAPER не изменены. Внешних биржевых POST и пользовательских виртуальных сделок не выполнялось. Остаточный риск: доступность реального upstream WS/браузера после deploy ещё требует проверки защищённого Preview.

[Мобильный график — локальный replay](mobile-chart.png) · [Desktop — локальный replay](desktop-chart.png) · [JSON](browser-result.json).

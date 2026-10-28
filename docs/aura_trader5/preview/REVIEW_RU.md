# Preview code/security review

Отдельные проходы: входные env → отдельный entrypoint → middleware owner/CSRF/
confirmation → существующий Manual Service → PreviewStore read-only guard →
ledger RPC. Нет импортов app.main/Active43 controller/scheduler (подтверждено
отдельным subprocess), нет автоматического scheduler или signal-to-order вызова.

HTTPX только fixed public Bitget и закреплённый preview Supabase host, redirects
запрещены, ответы/таймауты ограничены. Секреты только серверные env, repr скрывает
key/password, guard/ошибки не раскрывают исходные тела upstream. Runtime не имеет
Render/GitHub/Cloudflare полномочий. Env production/generic keys запрещены.

Production ref/service ID/hostname запрещены до сетевых клиентов. SQL bootstrap
требует пустой public schema и корректный не-production ref, rollback транзакции
на несовпадении. Reapply требует тот же marker/ref. Перед каждой ledger RPC —
attestation; чужой marker, другая таблица, неправильная роль, 401 не дают POST
ledger. Opaque ключи связывает с проектом Supabase gateway на pinned host;
локальное декодирование legacy JWT только deny-check, не авторизация.

Отдельный owner login на всей странице/assets/API. Только minimal health публичен.
Открытие/ручной close требуют существующий CSRF + preview ack; реальная кнопка
запрашивает подтверждение, отмена не отправляет запрос. При OPEN отдельно
разрешаются автоматические SL/TP. Без защитного worker новые OPEN блокируются.
Readiness не читает/seed ledger и не запускает protect/tick. Static allowlist не
позволяет отдавать production panel/datasets/SQL/env; HTML не содержит Active43.

Обнаруженные и исправленные несовместимости: публичный Analyst делал fetch с
credentials=omit, для защищённого preview добавлен только условный same-origin;
production default остаётся omit. Прежние production env как fallback не
используются. Ephemeral SQLite отвергнут как runtime persistence. Тестовый cloud
GH token удаляется только fixture, не ослабляя production credential gate.

Critical/high findings после исправлений не обнаружены. Ограничения: hosted
ключ/SQL/JWT gateway ещё не проверены; Free sleep не гарантирует SL/TP; общий
workspace quota может влиять на production, поэтому нужен отдельный workspace.
Ни одна локальная проверка не объявлена production/Render verified.

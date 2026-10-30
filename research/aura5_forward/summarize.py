"""Reproducible human-readable tables from retained real-archive outcomes."""
import csv
import datetime as dt
import gzip
import json
from pathlib import Path
from research.aura5_cost_audit.run import metrics

ROOT=Path('docs/aura_trader5/verified_forward')

def utc(t):return dt.datetime.fromtimestamp(t,dt.timezone.utc).isoformat()

def run():
    outcomes=json.loads(gzip.decompress((ROOT/'alternatives-outcomes.json.gz').read_bytes()))
    closed=[x for x in outcomes if x['cost_multiplier']==1 and x.get('entered') and x['outcome'] in ('TP','SL','TIMEOUT')]
    monthly=[]
    for family in sorted({r['strategy'] for r in outcomes}):
        for variant in ('BASE','STRICT'):
            for side in ('LONG','SHORT'):
                xs=[r for r in closed if (r['strategy'],r['variant'],r['direction'])==(family,variant,side)]
                for month in sorted({utc(r['signal_time'])[:7] for r in xs}):
                    monthly.append({'strategy':family,'variant':variant,'direction':side,'month':month,
                                    **metrics([r for r in xs if utc(r['signal_time'])[:7]==month])})
    (ROOT/'monthly.json').write_text(json.dumps(monthly,indent=2,allow_nan=False)+'\n')
    report=['# Aura 5.0 — проверенный исследовательский терминал','',
            '**NO_EDGE_FOUND. CONFIRMED запрещён; независимого неиспользованного holdout нет.**','',
            '## Что изменено','',
            '- Покрытие учитывает только пары успешных LIVE-сэмплов одной сессии с интервалом не более 15 секунд. Ошибки, рестарты и края окна считаются ненаблюдаемыми. Это дискретные проверки, а не непрерывная запись каждого тика.',
            '- WAIT/WATCH/CONFIRMED объяснены в интерфейсе. WATCH остаётся непроверенной гипотезой. Для текущей котировки показаны комиссии входа/выхода и резерв funding на независимый 1 BTC.',
            '- Health возвращает 503 при остановке или задержке наблюдателя более 120 секунд. Торговые функции не включались.',
            '- Добавлен ограниченный forward recorder с точными входами, хешами, повторным расчётом решений и сохранением покрытия. Он не является постоянно работающим сервисом.','',
            '## Причины отсутствия сигналов','',
            '229 кандидатов из PR #67 воспроизведены исходной моделью: 125 LONG / 104 SHORT. После исправлений PR #68 227 не проходят net RR/геометрию; два проходят RR, но не имеют технического триггера. Пороги и якоря Entry/SL/TP не менялись.','',
            'При низкой ATR фиксированные комиссии/slippage съедают значительную долю расстояния до TP; mean reversion и range часто имеют слишком близкую среднюю цель. Дополнительные обязательные признаки trend/retest/volume/RSI должны совпасть на одной закрытой свече. Это проверенные причины редкости, не повод ослаблять фильтры. Диагностика показывает отдельные причины по каждому семейству, TF и стороне.','',
            '## Воспроизведение исправленного replay','',
            'Все четыре файла `cost_audit/results` воспроизведены побайтно. 2026-08-01–2026-10-29 UTC: 43 технических плана, 42 закрытых гипотезы (27 LONG / 15 SHORT), одна исключена по overlap. Net −16924.83 USDT, PF 0.5706, expectancy −0.2546 gross-reference R; максимум падения суммы независимых 1 BTC-гипотез 19558.78 USDT (точное значение — в summary исходного аудита). Это не доходность или drawdown портфеля пользователя.','',
            '## Ограниченная проверка альтернатив','',
            'Протокол: шесть семейств × BASE/STRICT × только 4h = 12 конфигураций. Параметры уже существовали; подбора и выбора победителя нет. Каждое решение получает ровно 260 закрытых архивных баров. Границы времени разделены, позиции не переносятся; незакрытые на границе UNKNOWN. Все периоды уже исследовались ранее: reused final НЕ является holdout.','',
            '| Период | Вариант | Закрыто | LONG / SHORT | Net USDT | PF | Expectancy gross R | Max DD суммы 1 BTC |',
            '|---|---|---:|---:|---:|---:|---:|---:|']
    for split in ('train','validation','reused_test','reused_final_NOT_HOLDOUT'):
        for variant in ('BASE','STRICT'):
            xs=[r for r in outcomes if r['split']==split and r['variant']==variant and r['cost_multiplier']==1]
            m=metrics(xs);counts={side:sum(r.get('entered',False) and r['outcome'] in ('TP','SL','TIMEOUT') and r['direction']==side for r in xs) for side in ('LONG','SHORT')}
            def num(v):return '—' if v is None else f'{v:.4f}'
            report.append(f"| {split} | {variant} | {m['closed']} | {counts['LONG']} / {counts['SHORT']} | {num(m['net_pnl_usdt_per_independent_1btc'])} | {num(m['profit_factor'])} | {num(m['expectancy_common_gross_R'])} | {num(m['max_drawdown_sum_independent_1btc'])} |")
    report+=['','Полная частота на 30 дней, все family/side/split, stress ×1.5/×2 — `alternatives.json`; устойчивость по месяцам — `monthly.json`. Отсутствующие месяцы не считаются прибыльными; месяцы без закрытий не представлены. Метрики выше суммируют независимые перекрывающиеся гипотезы, а не моделируют капитал.','',
             '## Реальные технические примеры','',
             'Котировки из сохранённой истории Bitget. Вход/выход и расходы моделируются, реальные ордера не выставлялись. Время UTC. Примеры выбраны хронологически по стороне, а не по прибыли.','',
             '| Время | Сторона / стратегия / TF | Entry ref / fill | SL | TP | Net RR плана | Итог | Net USDT |',
             '|---|---|---:|---:|---:|---:|---|---:|']
    source=json.loads(gzip.decompress(Path('docs/aura_trader5/cost_audit/results/outcomes.json.gz').read_bytes()))
    examples=[];example_notes=[]
    for side in ('LONG','SHORT'):
        xs=sorted([r for r in source if r['audit_version']=='after' and r['cost_multiplier']==1 and r['direction']==side and r.get('entered')],key=lambda r:r['signal_time'])[:2]
        for r in xs:
            examples.append(r)
            report.append(f"| {utc(r['signal_time'])} | {side} / {r['strategy']} / {r['frame']} | {r['entry']:.2f} / {r['entry_fill']:.2f} | {r['sl']:.2f} | {r['tp']:.2f} | {r['net_rr']:.3f} | {r['outcome']} | {float(r['pnl_usdt']):.2f} |")
            example_notes+=['',f"Основания {r['id']}: {'; '.join(r['reasons'])}. Триггер: {r['confirmation']}. Отмена: {r['cancel']}. Комиссии {r['fees_usdt']}; funding {r['funding_usdt']} USDT.",'']
    report+=example_notes
    (ROOT/'examples.json').write_text(json.dumps(examples,indent=2,allow_nan=False)+'\n')
    report+=['','## Издержки и ограничения','',
             '10 bps комиссии/сторону, 5 bps slippage/сторону, модель полного спреда 2 bps; резерв funding 1 bp/8h. Это консервативные допущения, не тариф пользователя. Исторических Bid/Ask, fill и mark price нет; funding использует публичные ставки и OHLC notional proxy. Нет нового независимого holdout или доказанного преимущества.','',
             '## Forward, проверки и выпуск','',
             'Фактическая длительность, покрытие и результаты текущего запуска находятся в `public_capture/summary.json`. Начало после фиксации правил. Нет утверждения о 24/48 часах или достаточном числе сделок. Сбор продолжает уже установленный observer Preview, только когда Render не спит. Новые ресурсы, keep-alive обход сна, секреты и платежи не создавались.','',
             'Telegram в текущем сигнальном observer не интегрирован; доставка Telegram НЕ проверена. WATCH-звук opt-in уже существует: проверяется Chromium на синтетическом транспорте (жест, mute, stale, reconnect, dedup), а не выдаётся за реальную рыночную доставку или слышимость телефона.','',
             'Локальный полный Python до последних изменений: 2172 PASS / 5 PostgreSQL skips; актуальные full CI, Chromium и точный head — в PR. Локальная загрузка Chromium не удалась (получен некорректный ZIP), поэтому требуется удалённый CI. Не считать прежний CI проверкой нового head.','',
             'Отдельные проходы code review и security review: входы только публичные GET Bitget; research только локальные архивы; наблюдатель не получает account keys/исполнителей. Проверены same-session coverage, единицы USDT/BTC, причинность окон, независимые LONG/SHORT, расходы по executable-side quote, дедупликация, owner auth и неизменные eligibility/rules. Нерешённых critical/high в изменённом коде не найдено. Это отдельные review-проходы одного исполнителя, не внешняя независимая экспертиза.','',
             '## Действия на Bybit Demo','',
             '1. Откройте существующий Preview и войдите прежним owner-паролем. Убедитесь, что нужный TF свежий, а наблюдатель работает.',
             '2. Для уведомлений нажмите «Активировать звук», «Проверить звук», затем отдельно включите исследовательский WATCH. Держите вкладку открытой; звук при блокировке телефона не гарантируется.',
             '3. WAIT — ждать. WATCH-подготовка без technical trigger — только наблюдать. WATCH с триггером — учебная гипотеза, не подтверждённая прибыльная рекомендация.',
             '4. Если самостоятельно решили проверить гипотезу, откройте Bybit Demo вручную, BTCUSDT perpetual. Сверьте актуальную цену Bybit с зоной, срок, сторону, SL/TP и заново посчитайте риск с расходами Bybit. При выходе из зоны или устаревании пропустите сценарий. Цены разных бирж не взаимозаменяемы.',
             '5. В Aura не нажимайте BUY/SELL и не включайте PAPER/Active43. Перенос в ручную форму лишь заполняет поля; сделки и исходы в отчёте исследовательские.']
    # Obtain exact DD from saved audit instead of maintaining a rounded duplicate.
    totals=json.loads(Path('docs/aura_trader5/cost_audit/results/summary.json').read_text())['totals']
    dd=next(x['max_drawdown_sum_independent_1btc'] for x in totals if x['version']=='after' and x['cost_multiplier']==1)
    text='\n'.join(report).replace('19558.78',f'{dd:.2f}')+'\n'
    capture=json.loads((ROOT/'public_capture/summary.json').read_text())
    rows=[x for x in capture['records'] if x['plan']['technical_trigger']]
    forward_note=(f"\n\nФактический forward: {utc(capture['started_at'])} — {utc(capture['ended_at'])}, "
                  f"{capture['elapsed_seconds']:.3f} секунд, {capture['cycles']} полных циклов. "
                  f"Технических LONG {sum(x['plan']['direction']=='LONG' for x in rows)}, SHORT {sum(x['plan']['direction']=='SHORT' for x in rows)}, "
                  "WATCH 0, CONFIRMED 0, реальных звуковых/Telegram-доставок 0. "
                  "Верифицированы 5 точных входных окон: 5m ×2, остальные TF ×1. "
                  "5m: 2 LIVE / 16 QUOTE_GAP; 15m/1h/4h: по 18 LIVE. Последний ограниченный запрос был прерван дедлайном. "
                  "Это частичное наблюдение; не успешный непрерывный 5-минутный feed и не 24/48-часовой тест. "
                  "Старые котировки не выдавались за LIVE.\n")
    (ROOT/'REPORT_RU.md').write_text(text+forward_note+'''

## Исправление задержки котировки между TF

Исходный 300-секундный capture выше выполнен ДО этого исправления и сохранён неизменным. Найдено и тестом воспроизведено: gather ожидал самый медленный TF; Bid/Ask раннего 5m успевал устареть до Store.observe. Это вызывало QUOTE_GAP даже при наличии свежей котировки того же BTCUSDT из позднего ответа.

В цикле теперь выбирается самая свежая действительно полученная котировка того же SOURCE среди валидных ответов (frame/step проверены). Она одинаково используется для всех TF, поскольку Bid/Ask относится к инструменту, а не к длительности свечи. Биржевой timestamp и received_at не изменяются; лимит 5 секунд, закрытые бары, проверка cutoffs, источник и cost gates сохранены. Если свежих котировок нет, future/foreign/stale не допускаются. Точные обновлённые snapshots сохраняются и воспроизводятся audit_page.

Regression сначала воспроизвёл ошибку 5m=QUOTE_GAP, после исправления проходят все четыре native окна. Четыре отрицательных варианта (все старые, будущая котировка, чужой quote source, чужой snapshot source) остаются без записей/quotes. Целевой набор 73 PASS. Это исправление транспорта, не ослабление фильтров и не доказательство преимущества. Новые forward-данные учитываются отдельно от исходного capture.
''')

if __name__=='__main__':run()

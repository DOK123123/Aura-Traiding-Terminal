"""Derive compact review tables and a deterministic archive from offline results."""
import argparse,csv,gzip,hashlib,io,json,tarfile
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--primary',type=Path,required=True);p.add_argument('--full',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    full=json.loads((a.full/'summary.json').read_text());primary=json.loads((a.primary/'summary.json').read_text())
    for name,source in [('primary',a.primary),('full-minute',a.full)]:
        for file in ['summary.json','comparison.csv','signals.csv','trades.csv']:(a.output/(name+'-'+file)).write_bytes((source/file).read_bytes())
    rows=[]
    for scope,r in full['stats'].items():
        profile,segment=scope.split('/',1)
        for category in ['first_wait','all_failed','warnings']:
            for code,count in r[category].items():rows.append(dict(profile=profile,segment=segment,category=category,code=code,count=count,observations=r['observations'],percent=count/r['observations']*100))
    with (a.output/'wait-reasons.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    raw=io.BytesIO()
    with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,filename='') as gz:
        with tarfile.open(fileobj=gz,mode='w|') as t:
            for prefix,folder in [('primary',a.primary),('full-minute',a.full)]:
                for file in sorted(folder.iterdir()):
                    data=file.read_bytes();info=tarfile.TarInfo(prefix+'/'+file.name);info.size=len(data);info.mtime=0;info.mode=0o644;t.addfile(info,io.BytesIO(data))
    (a.output/'complete-results.tar.gz').write_bytes(raw.getvalue())
    def f(n):return 'N/A' if n is None else f'{n:.4f}'
    text='''# LIVE ANALYST: WAIT audit и два профиля

Исследование локальное, изолированное. Изменяются только ручной аналитик,
его UI, offline research и тесты в Draft PR #62. Production/Active43/Manual Paper
ledger/риски/SQL/баланс/позиции не изменяются. Автоматических входов нет.

## Подтверждённые причины

Старая функция делала ранний return после первого отказа. `CONFLICTING_4H`
означает строго противоположное направление EMA20/50 закрытого 4h, когда 5m,
15m и 1h уже совпали. Это запрограммированная консервативная политика, не ошибка
доставки сигнала. Младший тренд может измениться раньше инерционного 4h.
Старый экран не показывал последующие независимые невыполненные условия.

Добавлена полная матрица условий для LONG и SHORT. Отдельно отображаются
жёсткие запреты качества данных, обязательные условия входа и предупреждения
о риске. Условный план при WAIT не разрешает копирование/сделку. На неизвестных,
устаревших или неполных данных потенциальные планы тоже очищаются.

Исправлена несогласованность описания зоны: старая проверка цены разрешала
допуск 0,25 ATR за EMA/Fibonacci-зоной, но возвращала Entry zone без допуска.
Теперь отдельно возвращаются исходная confluence zone и фактическая допустимая
entry zone. Это не меняет LONG/SHORT/WAIT консервативного профиля: на всех
минутных наблюдениях расхождений с сохранённым `legacyAnalyze` — **0**.

## Правила, зафиксированные до первичного прогона

**Консервативный — профиль по умолчанию.** Прежние правила: закрытые EMA 5m/15m/1h
совпадают, 4h не противоположный, упорядоченный прошлый 15m импульс и совпадение
EMA20/Fibonacci, RSI LONG 52–68 / SHORT 32–48, восстановление тела текущей свечи,
частичный объём ≥1, MACD и net R/R ≥1,5. TP ограничен прошлым экстремумом/2,5R.

**Умеренный — отдельная, не подтверждённая гипотеза.** Та же согласованность трёх
закрытых трендов, те же RSI/тело/объём/MACD; вход после EMA20 pullback ±0,5 ATR
с прежним ценовым допуском 0,25 ATR. Fibonacci — контекст, не обязательная зона.
TP — явно обозначенная проекция 2,5R, не подтверждённый уровень. Противоположный
4h — предупреждение только при силе закрытого 1h |EMA20−EMA50|/ATR ≥0,5 и
net R/R ≥2; без них WAIT. В остальных случаях net R/R ≥1,5. Нельзя получить LONG
только выбором умеренного профиля: все обязательные условия остаются проверками.

Свежесть/source/UTC/пропуски/согласованность окон одинаковы для обоих профилей.
Серверные риски счёта не увеличиваются. Выбор профиля не отправляет POST.
Число выполненных условий — не вероятность прибыли.

## Протокол, данные и независимость

Первичный протокол `research/live_manual/profiles/protocol.json` зафиксирован
до просмотра новых результатов. Два профиля, без поиска комбинаций и изменений
порогов после результатов. Первично наблюдались минуты 1 и 4 внутри 5m.
Отдельный cadence audit зарегистрирован после этого отрицательного результата:
все минуты того же периода, без изменения стратегий. Это аудит покрытия,
не независимый OOS. Ни один прогон не использовался для выбора «победителя».

Официальные Bitget USDT-M BTCUSDT минутные ZIP June–September 2026, SHA-256 в
summary. 175680 непрерывных минут от 2026-05-31T16:00Z до 2026-09-30T16:00Z.
Месячная граница архива UTC+8, сами epoch timestamps UTC и не сдвигаются.
Пропусков/дубликатов нет. До 6 июля используется прогрев 200 закрытых 4h.
Оценка: **6 июля — 30 сентября 2026 16:00 UTC**, 86⅔ суток. Месячные денежные
срезы ниже независимы по моделируемому капиталу 10000 каждый, но не статистически.

Предыдущий реестр исследований уже использовал эти календарные даты. Также
неполон полный журнал прежних экспозиций. Поэтому **нового подтверждённого
независимого исторического OOS нет**. Новая биржа или новый файл не создают OOS.
Протокол содержит снимок старого реестра. Прогон не доказывает прибыльность.

Режимы классифицируются только по закрытому 1h: high-vol ATR/close ≥1%; иначе
тренд при |EMA20−EMA50|/ATR ≥0,5; иначе диапазон. Никакой разметки будущей ценой.

## Результаты

'''
    text+=f'Первично: **{primary["observations"]}** наблюдений. Полный минутный аудит: **{full["observations"]}**.\n\n'
    text+='| Профиль / период | LONG / SHORT наблюдений | Сделок | Net PnL USDT | Return % | PF | Win Rate % | Max DD % | Expectancy |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n'
    for profile in ['CONSERVATIVE','MODERATE']:
        for period in ['2026-07','2026-08','2026-09']:
            s=full['stats'][profile+'/'+period];m=full['results'][period+'_'+profile+'_1']
            text+=f'| {profile} / {period} | {s["states"]["LONG"]} / {s["states"]["SHORT"]} | {m["trades"]} | {f(m["net_pnl"])} | {f(m["return_pct"])} | {f(m["profit_factor"])} | {f(m["win_rate_pct"])} | {f(m["max_drawdown_pct"])} | {f(m["expectancy"])} |\n'
    text+='\nОба профиля: **0 сделок/день на минутных срезах**, не прогноз будущей tick-level частоты. '
    text+='При расходах ×1,5 и ×2 также 0 сделок: это не положительный стресс-тест прибыльности. Нулевые PnL/DD означают отсутствие экспозиции; PF/Win Rate/expectancy не определены.\n\n'
    text+='### Первые причины WAIT, полный минутный аудит\n\n| Причина | Консервативный | Умеренный |\n|---|---:|---:|\n'
    c=full['stats']['CONSERVATIVE/ALL'];m=full['stats']['MODERATE/ALL']
    for code in sorted(set(c['first_wait'])|set(m['first_wait'])):text+=f'| `{code}` | {c["first_wait"].get(code,0)} | {m["first_wait"].get(code,0)} |\n'
    text+=f'''\nСогласование закрытых EMA отсутствовало в {c['first_wait']['CLOSED_TREND_NOT_ALIGNED']} наблюдениях
({c['first_wait']['CLOSED_TREND_NOT_ALIGNED']/full['observations']*100:.2f}%). Первый отказ 4h —
{c['first_wait']['CONFLICTING_4H']} ({c['first_wait']['CONFLICTING_4H']/full['observations']*100:.2f}%). В полной матрице
4h конфликт встречался {c['conflicting_4h']} раз, но **единственным блокером — {c['only_4h_block']}**.
Снятие только этого запрета не создало бы подтверждённых входов на этих срезах.
Пересекающиеся all_failed/warnings в CSV нельзя складывать как взаимоисключающие
причины; часть R/R checks не вычисляется при отсутствии корректной геометрии.

### Расходы и масштаб стопа

Медианный ATR 5m — {full['quantiles']['CONSERVATIVE']['atr_pct']['p50']:.4f}% цены.
Расчётные полные расходы около 0,32% номинала за круг: fee 0,10%/сторону,
adverse slippage 0,05%/сторону, modeled spread 2 bps. Funding отсутствует.
Для гипотетических gross 2,5R и net 1,5R требуется примерно d ≥2,5c, то есть
стоп порядка 0,8% цены при c≈0,32%; это приближение, точные вычисления зависят
от входа/SL/TP. Короткий 5m ATR-стоп обычно существенно меньше этого масштаба.
Это объясняет экономический барьер, не позволяет просто отодвинуть TP без
независимого обоснования достижимости.

Во всех остальных условиях прошли консервативные {full['quantiles']['CONSERVATIVE']['rr_only_block']} наблюдения,
умеренные {full['quantiles']['MODERATE']['rr_only_block']}; все отклонены по net R/R.
У умеренных p50 net R/R этих {full['quantiles']['MODERATE']['all_other_checks_pass_rr']['n']} наблюдений =
{full['quantiles']['MODERATE']['all_other_checks_pass_rr']['p50']:.3f}, ниже 1,5/2. Более высокая частота потенциально
почти готовых конфигураций не стала положительным математическим ожиданием.

Существующий Manual Paper ledger использует fee 0,06%, аналитик — консервативные
0,10%. Это известное различие моделей, теперь явно написано в UI. В этой задаче
не менялись комиссии/риски ledger и не выбирался более дешёвый сценарий после
просмотра результатов. Реальная account-specific комиссия не проверена.

### Покрытие режимов

| Режим (из прошлых данных) | Минутных наблюдений | Доля % |\n|---|---:|---:|\n'''
    for regime in ['TREND_UP','TREND_DOWN','RANGE','HIGH_VOL']:
        n=full['stats']['CONSERVATIVE/'+regime]['observations'];text+=f'| {regime} | {n} | {n/full["observations"]*100:.2f} |\n'
    text+='''
Во всех режимах оба профиля дали 0 сделок, поэтому нет оценки различий PnL/PF
по режимам. High-vol покрыт особенно слабо. Минутные точки и соседние параметры
зависимы во времени: 124800 наблюдений не означают столько независимых испытаний.

## Причинность и исполнение

На t+3 секунды используются только завершённые предыдущие минуты и условная
доступная текущая open-цена. Текущие high/low/close/volume не видны до завершения
минуты. Происхождение реальное, но историческая availability предполагается,
не измерена; задержка +3с не быстрее +2с из input manifest. Исторических bid/ask
и внутриминутного пути нет, spread моделируется. Поэтому это minute-prefix proxy,
не точное воспроизведение 2Hz WS, и отсутствие сигналов не доказывает их полное
отсутствие на всех реальных тиках.

Чистый локальный simulator: сначала open/gap/старое принятое ручное намерение,
затем независимый текущий сигнал, затем неизвестный на момент решения диапазон
минуты и SL/TP. Нельзя использовать будущий close, чтобы заранее освободить
позицию. Вход — только следующий open не раньше 60с после принятия плана;
на данной сетке возможна задержка 117с. Это консервативная модель задержанного
ручного намерения, не обещание цены/TTL живого API. Риск/zone/RR переоцениваются
при fill, лот вниз, fee/slippage/spread на обе стороны, максимум одна позиция,
0,5%/2000 USDT/дневные 2%/10% потери исходного капитала. Нулевой итоговый объём
запрещает смоделированные fills как ex-post отсутствие prints, не как предиктор.
На dual touch SL первый, гэп неблагоприятен, favorable TP gap не улучшает target.
Закрытие в конце месячного среза — явно обозначенная оценка. Все реальные
исследовательские истории сделок пусты; независимые известные LONG/SHORT
численные тесты отдельно проверяют исполнение и комиссии.

## Вывод и следующий независимый эксперимент

**INSUFFICIENT_EVIDENCE. Прибыльность обоих профилей не доказана.** Нет оснований
объявлять умеренный профиль лучше или выбирать его ради частоты сигналов.
Консервативный остаётся default для совместимости, не потому что он прибыльный.

Практическое улучшение — видны BUY/SELL условные планы, конкретные недостающие
условия и ценовые зоны, все блокеры, separate 4h warning и реальный масштаб расходов.
WAIT больше не пустая сводка. Ни один условный план сам не создаёт виртуальную
сделку; при неготовом/устаревшем сценарии копирование по-прежнему запрещено.

Нужна будущая независимая проверка с реальным наблюдаемым bid/ask/receipt временем,
замороженными SHA/параметрами. Предлагаемая первая дата — 2026-10-29T00:00:00Z,
90 дней и минимум 100 непересекающихся закрытых планов; при меньшей выборке
результат остаётся неопределённым. Не перенастраивать те же кандидаты по этим
данным. Сбор/расписание/production PAPER не включались. Альтернативную экономику
более длинного горизонта следует исследовать отдельно, не растягивать SL/TP
текущего профиля ради прохождения R/R.

## Проверки и воспроизведение

```bash
PYTHONPATH=. python -m research.live_manual.profiles.prepare --input /path/to/official-archives --output /tmp/profiles-input-new.json
node research/live_manual/profiles/run.cjs --input /tmp/profiles-input-new.json --output /tmp/profiles-primary-new
node research/live_manual/profiles/run.cjs --input /tmp/profiles-input-new.json --output /tmp/profiles-full-new --all-minutes
python -m research.live_manual.profiles.report --primary /tmp/profiles-primary-new --full /tmp/profiles-full-new --output /tmp/profiles-report-new
node --test tests/*.cjs
python -m pytest -q
PYTHONPATH=. python scripts/verify_manual_live_browser.py --output-dir /tmp/profiles-browser-new
```

Входная папка: ранее проверенные четыре official ZIP и manifest.json из первого
replay #59/#62; точные имена/URL/SHA и нормализованный диапазон в summary.
Runner проверяет hash протокола/cadence и неизменность исходников во время прогона.
Полные equity/CSV лежат раздельно в complete-results.tar.gz; компактные сравнения,
таблицы WAIT и summary не упакованы в один огромный JSON.

Новые regression cases: 4h veto vs warning, усиленные условия против 4h,
LONG/SHORT, неизменный conservative state, свежесть/пропуски/источник обоих
профилей, условный WAIT-план, отсутствие приказов при profile switch,
каузальность/повтор/потери/fees/SL-first в offline model. Фактические результаты
финального CI и браузера — в описании PR. Физический Android не доступен;
проверены Chromium desktop и touch/mobile emulation. Production не проверялся.
'''
    (a.output/'REPORT_RU.md').write_text(text)
    digests={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output.iterdir() if p.is_file()};(a.output/'delivery-sha256.json').write_text(json.dumps(digests,indent=2)+'\n')
if __name__=='__main__':main()

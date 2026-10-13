"""Compact reproducible delivery; full auditable journals remain outside git."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.pattern_research import atomic_json,digest,source_hash,protocol
from scripts.run_pattern_research import compatible_protocol

COLUMNS=['trades','net_pnl','gross_filled_price_pnl','gross_raw_path_pnl','fees','slippage','turnover','win_rate','profit_factor','expectancy','average_win','average_loss']

def compact(row,stress=False):
    out=dict(row)
    if 'metrics' in out:
        out['metrics']={k:v for k,v in out['metrics'].items() if k not in ('sample_note','sharpe_assumptions')}
    if 'economy' in out:
        fields=('gross_filled_price_pnl','gross_raw_path_pnl','turnover','raw_turnover',
                'gross_profit_raw_price_basis','gross_loss_raw_price_basis',
                'holding_seconds','rounding_residual','fixed_path_fee_break_even_bps')
        out['economy']={k:v for k,v in out['economy'].items() if k in fields}
    if stress:
        for key in ('by_month','by_direction','by_regime'):out.pop(key,None)
    for key in ('by_month','by_year','by_direction','by_regime'):
        if key in out:out[key]={label:[values.get(k) for k in COLUMNS] for label,values in out[key].items()}
    if 'stress' in out:out['stress']=compact(out['stress'],True)
    return out


def report(output,path,markdown):
    full_path=output/'full-report.json'
    raw=json.loads(path.read_text()) if not full_path.exists() else json.loads(full_path.read_text())
    if not compatible_protocol(raw['protocol'],protocol()):raise ValueError('REPORT_SOURCE_CHANGED')
    if raw['status'].startswith('INCOMPLETE'):raise ValueError('RESEARCH_NOT_FINISHED')
    state=json.loads((output/'checkpoint.json').read_text())
    if not full_path.exists():atomic_json(full_path,raw)
    for period in ('development','validation','holdout'):
        for row in raw[period]:
            for stress in (False,True):
                scope='holdout_reused' if period=='holdout' else period
                key=row['hypothesis']['id']+'|'+scope+(' |stress' if stress else ' |base')
                record=state['jobs'][key];target=row['stress'] if stress else row
                target['artifact']=dict(filename=record['artifact'],sha256=record['sha256'])
    delivery=dict(raw)
    for period in ('development','validation','holdout'):delivery[period]=[compact(r) for r in raw[period]]
    if 'controls' in delivery:
        delivery['controls']=dict(delivery['controls'])
        for scope in ('controls','walk_forward'):
            delivery['controls'][scope]=[compact(r) for r in delivery['controls'][scope]]
    delivery['development_ranking']=[r['hypothesis']['id'] for r in sorted(raw['development'],key=lambda x:(-float(x['metrics']['net_profit']),x['hypothesis']['id']))]
    delivery['validation_ranking']=[r['hypothesis']['id'] for r in sorted(raw['validation'],key=lambda x:(-float(x['metrics']['net_profit']),x['hypothesis']['id']))]
    delivery['holdout_ranking']=[] if not raw['holdout'] else [r['hypothesis']['id'] for r in sorted(raw['holdout'],key=lambda x:(-float(x['metrics']['net_profit']),x['hypothesis']['id']))]
    delivery['grouped_economy_columns']=COLUMNS
    delivery['metric_definitions']={k:raw['development'][0]['metrics'][k] for k in ('sample_note','sharpe_assumptions')}
    delivery['full_aggregate_sha256']=hashlib.sha256(full_path.read_bytes()).hexdigest()
    delivery['source_commit']='8de193cce7a87723acb9d11a109398e63c5b7aac'
    delivery['independent_audit']=json.loads((output/'independent.audit.json').read_text())
    delivery['independent_control_audit']=json.loads((output/'independent.controls.audit.json').read_text()) if (output/'independent.controls.audit.json').exists() else {'status':'NOT_RUN'}
    delivery['checks']=json.loads((output/'checks.json').read_text()) if (output/'checks.json').exists() else {'status':'NOT_RUN_IN_THIS_RUN'}
    delivery['artifact_directory']='External offline run directory; reproduce via documented commands, not deployed to Render.'
    atomic_json(path,delivery)
    dev=raw['development'];val=raw['validation'];stages=Counter(x['classification'] for x in dev)
    good=[x for x in dev if float(x['metrics']['net_profit'])>0 and x['full_period_execution_valid']]
    lines=['','## Фактически завершённый расчёт','',
        f"Статус: **{raw['status']}**. Проверены 30 зарегистрированных детекторов на трёх TF; 810 development-гипотез, baseline+stress. Development-классы: `{dict(stages)}`.",
        f"Положительный полностью наблюдаемый development net: {len(good)} из810. Validation: {len(val)} описательных прогонов плюс stress; финалисты: {len(raw['finalists'])}; trading-прогоны2025: {len(raw['holdout'])}.",
        f"Всего primary jobs: {raw['completed_jobs']}. Сумма closed trades по810 baseline-гипотезам: {sum(r['metrics']['trades'] for r in dev)}. Это сумма разных симуляций с пересечениями, не число независимых рыночных событий.",
        f"Protocol SHA256: `{raw['protocol_sha256']}`; finalists lock SHA256: `{raw['holdout_lock_sha256']}`.",
        '', '### Top10 development — числовой рейтинг, не список разрешённых стратегий','',
        '| ID | Net USDT | Trades | Class | Причины |','|---|---:|---:|---|---|']
    for r in raw['top10_development']:lines.append(f"| {r['id']} | {r['net']} | {r['trades']} | {r['classification']} | {', '.join(r['reasons'])} |")
    lines.extend(['','### Validation','', '| ID | Net USDT | Trades | PF | DD% | Class/scope |','|---|---:|---:|---:|---:|---|'])
    for r in val:
        m=r['metrics'];lines.append(f"| {r['hypothesis']['id']} | {m['net_profit']} | {m['trades']} | {m['profit_factor']} | {m['max_drawdown_pct']} | {r['classification']} / {r['scope']} |")
    lines.extend(['','### Причины отбраковки','',f"`{raw['rejection_reasons']}`. Причины могут пересекаться; суммы не являются числом отдельных гипотез."])
    if not raw['finalists']:lines.extend(['','**Финалистов нет; 2025 не использован для поиска победителя. ПОДТВЕРЖДЁННОЙ ПРИБЫЛЬНОЙ СТРАТЕГИИ НЕТ.** Положительные числовые development-результаты не выдерживают заданный набор статистических, календарных или стресс-критериев. Не ослаблять пороги для красивого результата.'])
    controls=raw.get('controls',{})
    lines.extend(['','### Контроли и walk-forward','',f"Контрольных симуляций: {len(controls.get('controls',[]))}; walk-forward folds: {len(controls.get('walk_forward',[]))}. Полные результаты в JSON.", '', '| TF | Test year | Net USDT | Trades | Выбор только по прошлому |','|---|---:|---:|---:|---|'])
    for r in controls.get('walk_forward',[]):
        if 'metrics' in r:lines.append(f"| {r['timeframe']} | {r['test_year']} | {r['metrics']['net_profit']} | {r['metrics']['trades']} | {r['selected_from_past']['id']} |")
    lines.extend(['','### Независимая проверка и ограничения','',f"Accounting audit: `{delivery['independent_audit']}`.",f"Control audit: `{delivery['independent_control_audit']}`.",f"Checks: `{delivery['checks']}`.",
        'Полные journals и candle-level equity curves находятся внеgit в сжатых hash-addressed artifacts; воспроизводятся командами выше. JSON содержит все810 гипотез, агрегаты, hashes, подробную data-quality карту и occurrences. Grouped economy arrays имеют схему grouped_economy_columns; yearly/monthly PnL — атрибуция закрытых сделок по exit date, не отдельные ежегодно перезапущенные портфели.',
        'Walk-forward контрольный числовой выбор также не превращается в production-кандидата автоматически. Интервалы/пороговые detec­tors и блок14 дней — исследовательские допущения. Нет независимой гарантии edge, нет multiple-testing-adjusted новой2025 проверки.',
        'Следующий безопасный шаг: заранее определить новый отложенный forward-период, собрать данные и проверять небольшое число заранее обоснованных механизмов/микроструктурных гипотез. Ничего не включать в Auto Paper по этой сетке.',
        'Render, Android/live UI в этой задаче не проверялись и не изменялись.'])
    existing=markdown.read_text();prefix=existing.split('\n## Фактически завершённый расчёт')[0]
    markdown.write_text(prefix+'\n'.join(lines)+'\n')
    print('Compact report bytes',path.stat().st_size)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--markdown',type=Path,required=True);a=p.parse_args();report(a.output,a.report,a.markdown)

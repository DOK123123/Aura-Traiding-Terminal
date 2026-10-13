"""Auditable compact delivery, unchanged old reports and no runtime integration."""
import argparse,json,hashlib,sys
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.pattern_research import atomic_json
from research.market_intelligence.pipeline import protocol
from app.lab.models import digest
from scripts.run_pattern_research import artifact_read


def report(out,path,markdown):
    full=out/'full.report.json'
    data=json.loads((full if full.exists() else path).read_text())
    if data['status'].startswith('INCOMPLETE'):raise ValueError('RUN_NOT_FINISHED')
    if digest(data['protocol'])!=digest(protocol(ROOT)):raise ValueError('SOURCE_CHANGED')
    if not full.exists():atomic_json(full,data)
    data['independent_audit']=json.loads((out/'independent.audit.json').read_text())
    data['evaluation_policy']='Prequential completed-history memory, including earlier resolved validation events; normalizer and all parameters frozen. Not frozen-training-bank blind OOS.'
    data['checks']=json.loads((out/'checks.json').read_text()) if (out/'checks.json').exists() else dict(status='NOT_RUN_IN_THIS_RUN')
    meta=json.loads((out/'states.json.meta.json').read_text());states=artifact_read(out/'states.json.gz',meta['sha256'])
    by_year=defaultdict(Counter);clipped=Counter();available=0;calibration=Counter()
    for part in states:
        for row in part['rows']:
            if row is None:continue
            from datetime import datetime,timezone
            y=str(datetime.fromtimestamp(row['timestamp']-1,timezone.utc).year);by_year[y]['closed_states']+=1
            by_year[y]['pivot_confirmations']+=len(row['confirmed_pivots'])
            by_year[y]['known_mtf']+=row['mtf']['known_mask']==3
            for key in ('breakout','failed_breakout','retest','liquidity_sweep'):
                if row[key]:by_year[y][key]+=1
            if row['timestamp']<=data['normalizer']['fit_closed_through']:
                calibration['states']+=1;calibration['h1_available']+=row['mtf']['h1'] is not None;calibration['h4_available']+=row['mtf']['h4'] is not None
            if row['timestamp']>data['normalizer']['fit_closed_through']:
                available+=1
                for name,x,m,s in zip(data['normalizer']['features'],row['vector'],data['normalizer']['means'],data['normalizer']['scales']):
                    if abs((x-m)/s)>5:clipped[name]+=1
    del states
    data['calibration_availability']=dict(calibration)
    data['context_by_year']={k:dict(v) for k,v in sorted(by_year.items())}
    data['normalization_shift']=dict(evaluated_states=available,clipped_counts=dict(clipped),note='Descriptive clipping counts with frozen2020Q1 scaler; no refit to improve validation.')
    atomic_json(path,data)
    lines=['','## Фактический завершённый результат','',f"**{data['status']}**. Source protocol SHA256 `{data['protocol_sha256']}`.",
        f"Закрытых причинных состояний: {data['state_statistics']['closed_states']}; source candles2020–2024: {data['state_statistics']['source_candles']}. Label statistics: `{data['label_statistics']}`.",
        f"Проверены шесть стратегий+общий router,42 конфигурации,84 phase-results baseline/stress. Всего completed portfolios: {data['completed_jobs']}, кандидат одновременно development+validation: {len(data['candidates'])}.",
        f"Classes всех phase-results: `{data['results_classes']}`. Ни RULE, ни NEAREST baseline не активируется. 2025 не использован для новой trading performance.",
        '', '| ID | Development net USDT | Validation net USDT | Trades dev/val | Stress val | Class dev/val |','|---|---:|---:|---:|---:|---|']
    paired=defaultdict(dict)
    for r in data['results']:paired[r['hypothesis']['id']][r['period']]=r
    ranked=sorted(paired,key=lambda h:float(paired[h]['development']['base']['metrics']['net_profit']),reverse=True)
    for h in ranked[:10]:
        d=paired[h]['development'];v=paired[h]['validation'];dm=d['base']['metrics'];vm=v['base']['metrics']
        lines.append(f"| {h} | {dm['net_profit']} | {vm['net_profit']} | {dm['trades']}/{vm['trades']} | {v['stress']['metrics']['net_profit']} | {d['classification']}/{v['classification']} |")
    lines.extend(['','### Ненулевые лучшие numerical результаты, не победители',''])
    for period in ('development','validation'):
        active=[r for r in data['results'] if r['period']==period and r['base']['metrics']['trades']>0]
        best=max(active,key=lambda r:float(r['base']['metrics']['net_profit'])) if active else None
        if best:lines.append(f"{period}: `{best['hypothesis']['id']}`, net {best['base']['metrics']['net_profit']} USDT, trades {best['base']['metrics']['trades']}, class {best['classification']}, reasons `{best['reasons']}`.")
        else:lines.append(period+': no actual entries; no numerical profitability inference.')
    edge=[r for r in data['results'] if r['hypothesis']['mode']=='EDGE'];lines.append(f"\nEDGE router configurations: {len(edge)} phase-results; actual closed trades sum {sum(r['base']['metrics']['trades'] for r in edge)}. Повторные симуляции не независимые наблюдения.")
    if not data['candidates']:lines.append('\n**ПОДТВЕРЖДЁННОГО ПРЕИМУЩЕСТВА НЕТ.** WAIT является корректным результатом. Ноль сделок/мало аналогов — недостаток evidence, а не доказательство отрицательной доходности каждого возможного setup.')
    else:lines.append('\nRESEARCH_CANDIDATE — только исторический исследовательский статус, не proof прибыльности. Forward period и ручной review обязательны; ничего не активировано.')
    lines.extend(['','### Результаты по годам и ограничения','',f"State census: `{data['context_by_year']}`.",
        'Financial yearly/monthly metrics, Long/Short, regimes, gross/net,fees/slippage/turnover,DD,expectancy иbootstrap находятся в JSON для каждого portfolio. Полные journals/curves — внешние gzip artifacts сSHA в каждом результате; пересоздаются CLI, не публикуются как миллионы строк.',
        f"Clipping: `{data['normalization_shift']}`.",f"Calibration availability: `{data['calibration_availability']}`.",
        'В2020Q1 после gap/warmup не было доступных250-bar4h состояний: h4 mean0, scale floor0.1. Поэтому124064 последующих h4 значений clip в+-5. Это существенное ограничение metric/calibration, не основание менять параметры после просмотраvalidation. Следующий заранее фиксированный исследовательский протокол должен отдельно проверить categorical encoding и expanding past-only calibration на development folds.',
        'Per-period signal и risk refusals видны в financial results; decision_audit — общий counter source dataset, не сумма независимых observations. Label cost rejections отделены от unknown gap outcomes.',
        f"Independent audit: `{data['independent_audit']}`.",f"Checks: `{data['checks']}`.",
        'Рекомендация: новый заранее зафиксированный forward dataset, проверка calibration robustness только на past development folds и минимального числа механизмов; не ослаблять thresholds после просмотраvalidation. Нативный интерфейс/owner-подтверждение и execution остаются прежними. Никаких автоматических включений.',
        'Фактический Render/Android/live UI test NOT RUN; среда установленных dependencies отличается от requirements, полный pytest недоступен.'])
    prefix=markdown.read_text().split('\n## Фактический завершённый результат')[0]
    markdown.write_text(prefix+'\n'.join(lines)+'\n');print('Report bytes',path.stat().st_size)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--markdown',type=Path,required=True);a=p.parse_args();report(a.output,a.report,a.markdown)

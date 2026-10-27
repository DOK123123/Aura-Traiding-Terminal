"""Compact report plus separate bounded CSV/SVG artifacts. No web/DB writes."""
from collections import Counter
from decimal import Decimal as D
from pathlib import Path
from datetime import datetime,timezone
import csv,json,html


def utc(t):return datetime.fromtimestamp(t,timezone.utc).isoformat().replace('+00:00','Z')


def csv_file(path:Path,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r)) or ['status']
    with path.open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def chart(path,curve,title,drawdown=False):
    values=[float(p['equity']) for p in curve]
    if drawdown:
        peak=values[0];dd=[]
        for v in values:peak=max(peak,v);dd.append((v/peak-1)*100)
        values=dd
    step=max(1,len(curve)//2000)
    indices=sorted(set(list(range(0,len(curve),step))+[len(curve)-1,values.index(min(values)),values.index(max(values))]))
    lo=min(values);hi=max(values);span=hi-lo or 1;duration=max(1,curve[-1]['time']-curve[0]['time'])
    coords=' '.join(f"{40+(curve[i]['time']-curve[0]['time'])/duration*920:.2f},{350-(values[i]-lo)/span*300:.2f}" for i in indices)
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 400"><rect width="1000" height="400" fill="#111720"/><text x="30" y="28" fill="#dce5ef">{html.escape(title)}</text><polyline fill="none" stroke="#42d6b0" stroke-width="2" points="{coords}"/><text x="30" y="390" fill="#a0aec0">{lo:.4f} … {hi:.4f} · {utc(curve[0]["time"])} — {utc(curve[-1]["time"])}</text></svg>'
    path.write_text(svg)


def persist_run(folder:Path,name:str,result:dict):
    csv_file(folder/(name+'-trades.csv'),result['trades'])
    csv_file(folder/(name+'-events.csv'),result['events'])
    curve=result['equity_curve']
    sampled=[p for i,p in enumerate(curve) if i in (0,len(curve)-1) or p['time']%300==0]
    csv_file(folder/(name+'-equity.csv'),sampled)
    chart(folder/(name+'-equity.svg'),curve,name+' · liquidation equity USDT')
    chart(folder/(name+'-drawdown.svg'),curve,name+' · drawdown % (sampled plot)',True)
    return {k:v for k,v in result.items() if k not in ('trades','equity_curve','events')}


def markdown(summary):
    lines=['# Aura Backtest Lab 1.0 — offline replay','',
        'Это модель исторического исполнения, не реальные сделки и не проверка production.',
        'Вердикт: **INSUFFICIENT_EVIDENCE**. Прибыльность не подтверждена независимо.',
        '',f"Источник: `{summary['source']}`. Файл данных: `{summary['data_hash']}`.",
        f"Config: `{summary['config_hash']}`; code: `{summary['code_hash']}`.",
        '', '| Период / расходы | Сделки L/S | WR % | Net USDT | Return % | PF | Max DD % | Expectancy | B&H full / capped USDT |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for key,result in summary['runs'].items():
        m=result['metrics'];bh=result['benchmark']
        label=key.replace('test-','test_reused-',1) if key.startswith('test-') and summary['splits'][-1]['independence']=='NOT_INDEPENDENT' else key
        def val(v):return 'undefined' if v is None else str(v)
        lines.append(f"| {label} | {m['trades']} ({m['long_trades']}/{m['short_trades']}) | {val(m['win_rate'])} | {m['net_profit']} | {m['return_pct']} | {val(m['profit_factor'])} | {m['max_drawdown_pct']} | {val(m['expectancy'])} | {bh.get('full_capital',{}).get('net_profit','undefined')} / {bh.get('notional_2000',{}).get('net_profit','undefined')} |")
    lines+=['','## Периоды и независимость','']
    for s in summary['splits']:
        lines.append(f"- {s['name']}: {utc(s['start'])} — {utc(s['end'])} exclusive; **{s['independence']}**; {', '.join(s['reasons']) or 'только заявленный реестр, не внешняя аттестация'}.")
    lines+=['','## Решения и ограничения','',f"Закрытых 5m решений: {summary['decisions']}; подтверждённых LONG/SHORT: {summary['signals']}.",
        'Причины решений: `'+json.dumps(summary['decision_reasons'],ensure_ascii=False)+'`.','',
        'Сигналы/решения, события, сделки и equity хранятся отдельными CSV. Equity/Drawdown SVG — иллюстрация; метрики считаются по полной минутной кривой и opening marks, не по прореженному графику.',
        '',*['- '+x for x in summary['limitations']],
        '', 'Никаких изменений PAPER/Active43/production, БД, scheduler, ключей или ордеров.']
    return '\n'.join(lines)+'\n'

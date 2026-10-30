"""Deterministic closed-window rule replay; no live quotes, delivery or profit claim."""
from collections import Counter
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys

from app.hunter.engine import Prepared,FAMILIES
from app.hunter.store import MODEL_HASH
from app.hunter.market import STEPS,SOURCE
from app.hunter.diagnostics import explain,utc,DIAGNOSTICS_HASH
from research.hunter6.data import load,aggregate

START=int(dt.datetime(2026,10,27,tzinfo=dt.timezone.utc).timestamp())
END=int(dt.datetime(2026,10,29,tzinfo=dt.timezone.utc).timestamp())


def run(destination):
    out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    rows,_,manifest=load()
    rows=[r for r in rows if START-261*max(STEPS.values())<=r[0]<END]
    decisions=[];frames={}
    for frame,step in STEPS.items():
        aggregated=aggregate(rows,step);count=0
        for i,row in enumerate(aggregated):
            cutoff=row[0]+step
            if i<259 or not START<=cutoff<END:continue
            p=Prepared(aggregated[i-259:i+1],frame);plans=[]
            for family in FAMILIES:plans.extend(p.plans(259,family,cutoff=cutoff,watch=True))
            trace=explain(p,plans,cutoff,MODEL_HASH,replay=True)
            if any(r['trace_integrity']!='OK' for r in trace):raise ValueError('RULE_TRACE_PARITY_FAILED')
            decisions.extend(trace);count+=1
        frames[frame]=count
    windows={}
    for hours in (24,48):
        groups=[]
        for frame in STEPS:
            for family in FAMILIES:
                for side in ('LONG','SHORT'):
                    rs=[r for r in decisions if r['closed_candle_close']>=END-hours*3600 and (r['frame'],r['strategy'],r['direction'])==(frame,family,side)]
                    groups.append({'strategy':family,'frame':frame,'direction':side,'candles_evaluated':len(rs),
                        'candidates':sum(r['candidate'] is True for r in rs),'rule_plans':sum(r['rule_plan'] for r in rs),
                        'technical_triggers':sum(r['rule_plan'] and r['technical_trigger'] for r in rs),
                        'planning_rejected':sum(r['state']=='REJECTED' for r in rs),
                        'reason_codes':dict(sorted(Counter(c for r in rs for c in r['reason_codes']).items()))})
        windows[str(hours)]={'start_utc':utc(END-hours*3600),'end_exclusive_utc':utc(END),'groups':groups}
    summary={'scope':'AURA5_ARCHIVE_RULE_REPLAY_NOT_FORWARD','source':SOURCE,'start_utc':utc(START),'end_exclusive_utc':utc(END),
        'model_sha256':MODEL_HASH,'diagnostics_sha256':DIAGNOSTICS_HASH,'archive_manifest_sha256':hashlib.sha256(Path('data/hunter6/acquisition.json').read_bytes()).hexdigest(),
        'input_contract':'ARCHIVE_AGGREGATED_260_DIAGNOSTIC_ONLY','seed_bars':260,'frames':frames,'decisions':len(decisions),
        'sides_evaluated':['LONG','SHORT'],'windows':windows,'bid_ask_observed':False,'live_deliveries':None,
        'profitability_evaluated':False,'forward_24_48h':'NOT_RUN_NO_CONTINUOUS_HOSTING','actual_forward_uptime_seconds':None,
        'forward_coverage':None,'orders':0,'confirmed_registry_changes':0,'parameter_changes':0}
    raw=json.dumps(decisions,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    trace=gzip.compress(raw,mtime=0);(out/'decisions.json.gz').write_bytes(trace)
    summary['trace_sha256']=hashlib.sha256(trace).hexdigest()
    (out/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    columns=['hours','strategy','frame','direction','candles_evaluated','candidates','rule_plans','technical_triggers','planning_rejected','reason_codes']
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
    for hours,data in windows.items():
        for r in data['groups']:writer.writerow({'hours':hours,**r,'reason_codes':json.dumps(r['reason_codes'],sort_keys=True)})
    (out/'counts.csv').write_text(stream.getvalue())
    report=['# Aura 5.0 · Issue #66: детерминированный replay','',
        'Это диагностика правил на реальных архивных Bitget OHLCV, не LIVE/forward и не backtest прибыльности. Native Bid/Ask на прошлом периоде неизвестны: их возраст — null, котировки не выдумываются. REPLAY_PLAN не является доставленным WATCH.',
        '',f'Период: {utc(START)} — {utc(END)} (конец исключён). Окна: {frames}; решений по семейству/стороне: {len(decisions)}. Обе стороны проверяются на каждой закрытой свече. Параметры/реестр не менялись, ордеров 0.',
        '', 'Полноценный непрерывный 24–48h server observer здесь **NOT RUN**: текущий Free hosting засыпает, новый код не развёртывался. Uptime/coverage — неизвестны, не 24/48 часа. Будущий интерфейс показывает фактически записанные интервалы, gaps и смену журнала.',
        '', 'Таблица ниже: числа относятся только к указанным архивным окнам. Нет данных о реальной доставке звука, подтверждениях владельца или исполнении сделок.','']
    for hours,data in windows.items():
        report+=['## '+hours+' часа','', '| Семейство / TF / сторона | Свечи | Кандидаты | План / trigger | Planning rejected | Основные причины |','|---|---:|---:|---:|---:|---|']
        for r in data['groups']:
            reasons=', '.join(k+': '+str(v) for k,v in sorted(r['reason_codes'].items(),key=lambda x:(-x[1],x[0]))[:3])
            report.append(f"| {r['strategy']} / {r['frame']} / {r['direction']} | {r['candles_evaluated']} | {r['candidates']} | {r['rule_plans']} / {r['technical_triggers']} | {r['planning_rejected']} | {reasons} |")
    (out/'REPLAY_RU.md').write_text('\n'.join(report)+'\n')
    return summary


if __name__=='__main__':
    s=run(sys.argv[1] if len(sys.argv)>1 else 'docs/aura_trader5/issue66/replay')
    print(json.dumps({'frames':s['frames'],'decisions':s['decisions'],'trace_sha256':s['trace_sha256'],
                      'rule_plans_48h':sum(r['rule_plans'] for r in s['windows']['48']['groups']),
                      'technical_triggers_48h':sum(r['technical_triggers'] for r in s['windows']['48']['groups'])}))

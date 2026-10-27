"""python -m research.manual_analyst_replay --manifest ... --protocol ... --output NEW_DIR"""
import argparse
from bisect import bisect_left
from collections import Counter
from dataclasses import asdict
from decimal import Decimal as D
from pathlib import Path
import hashlib,json,os,shutil,tempfile,time
from . import VERSION
from .config import digest
from .dataset import load,sha256,SOURCE
from .adapter import build
from .execution import execute
from .protocol import validate_protocol,splits
from .report import csv_file,persist_run,markdown

ROOT=Path(__file__).resolve().parents[2]


def analyst_hash():
    return digest({name:sha256(ROOT/'app'/name) for name in ('aura_trader5_scenarios.py','aura_trader5_analysis.py','aura_trader5_technical.py','models.py')})


def code_hash():
    files=list(Path(__file__).parent.glob('*.py'))+[ROOT/'app'/name for name in (
        'aura_trader5_scenarios.py','aura_trader5_analysis.py','aura_trader5_technical.py','models.py','lab/execution.py','lab/models.py')]
    return digest({str(f.relative_to(ROOT)):sha256(f) for f in sorted(files)})


def run(manifest_path:Path,protocol_path:Path,output:Path):
    if os.getenv('RENDER') or os.getenv('CF_WORKER'):raise ValueError('OFFLINE_ONLY')
    output=output.resolve()
    if output.exists():raise ValueError('OUTPUT_ALREADY_EXISTS')
    # CLI may create only a NEW research directory, never app/static/config data.
    if output.is_relative_to(ROOT) and not any(output.is_relative_to(ROOT/p) for p in ('research_outputs','docs/aura_trader5/backtest_lab/results')):
        raise ValueError('UNSAFE_OUTPUT_DIRECTORY')
    if protocol_path.stat().st_size>2*1024*1024:raise ValueError('PROTOCOL_TOO_LARGE')
    protocol=json.loads(protocol_path.read_text())
    from .config import Config
    config=Config(**protocol['config']);config.validate();deadline=time.monotonic()+config.deadline_seconds
    data=load(manifest_path,config.max_rows)
    config=validate_protocol(protocol,data.execution[-1].time+data.execution_step)
    if protocol.get('analyst_code_hash')!=analyst_hash():raise ValueError('ANALYST_SOURCE_CHANGED_SINCE_FREEZE')
    source_hash=code_hash()
    signal_rows,decisions=build(data,config,protocol['start'],protocol['end'],deadline)
    periods=splits(protocol,data.manifest)
    times=[b.time for b in data.execution]
    summary=dict(version=VERSION,source=SOURCE,data_hash=data.data_hash,manifest_sha256=sha256(manifest_path),
        protocol_hash=digest(protocol),config_hash=config.hash,code_hash=source_hash,config=config.data(),
        splits=periods,decisions=len(decisions),signals=len(signal_rows),decision_reasons=dict(Counter(d['reason'] for d in decisions)),
        data_quality=dict(execution_rows=len(data.execution),execution_step=data.execution_step,first=data.execution[0].time,
            end=data.execution[-1].time+data.execution_step,frames={tf:len(rows) for tf,rows in data.frames.items()},
            duplicates=0,gaps=0,available_at_mode=data.manifest['availability_mode'],data_kind=data.manifest['data_kind']),
        runs={},verdict='INSUFFICIENT_EVIDENCE',production_changed=False,real_money_execution='DISABLED',limitations=[
            'История и все показатели — исследовательские; независимость test определяется полным календарным реестром, не новой биржей/файлом.',
            'Историческое время публикации не наблюдалось: close+delay — явное допущение архивного набора.',
            'OHLC open не гарантирует Bitget fill: следующий доступный минутный open + adverse spread/slippage + tick rounding — модель.',
            'Нет достоверной полной совместной истории funding + mark prices; funding NOT_INCLUDED. Итог не является PnL после всех возможных расходов.',
            'Контрактные tick/lot/min-notional приняты фиксированными допущениями; их исторические изменения и ликвидность L2 не доказаны.',
            'Стопы моделируются по минутному OHLC, SL имеет приоритет при SL+TP; гэп может превысить риск 0.5% и лимит просадки.',
            'Дневной лимит и drawdown guard наблюдают modeled minute OPEN marks; закрытые marks используются для статистики, не для решения на более раннем open.',
            'Дневная база equity фиксируется первым минутным open UTC-дня. Guard-выход — следующий доступный open после задержки; круглосуточное исполнение не доказано.',
            'SEGMENT_END_LIQUIDATION_ESTIMATE — принудительная бухгалтерская оценка конца сегмента, не гарантированный торгуемый close.',
            'Каждый сегмент начинает с 10000 USDT, позиции не переносятся через границы. B&H full — иной риск/exposure; capped B&H и cash даны отдельно.',
            'Стресс расходов повторно применяет risk/RR guards к тем же frozen signals; набор исполненных сделок может различаться.',
            'Нет реальных котировок bid/ask, L2/liquidations, leverage>1, funding или exchange orders. VectorBT не установлен.'])
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='.aura-replay-',dir=output.parent))
    try:
        csv_file(temporary/'decisions.csv',decisions)
        csv_file(temporary/'signals.csv',[{k:str(v) if isinstance(v,D) else v for k,v in asdict(s).items()} for s in signal_rows])
        for period in periods:
            bars=data.execution[bisect_left(times,period['start']):bisect_left(times,period['end'])]
            if not bars:raise ValueError('EMPTY_SPLIT')
            sig=[s for s in signal_rows if period['start']<=s.available_at<period['end']]
            for mult in ('1','1.5','2'):
                name=period['name']+'-cost'+mult
                result=execute(bars,data.execution_step,sig,config,cost_multiplier=D(mult),deadline=deadline)
                summary['runs'][name]=persist_run(temporary,name,result)
        if code_hash()!=source_hash:raise ValueError('CODE_CHANGED_DURING_REPLAY')
        (temporary/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
        (temporary/'REPORT_RU.md').write_text(markdown(summary))
        (temporary/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
        files={p.name:sha256(p) for p in temporary.iterdir()}
        (temporary/'artifact_hashes.json').write_text(json.dumps(files,indent=2)+'\n')
        if output.exists():raise ValueError('OUTPUT_ALREADY_EXISTS')
        temporary.rename(output)
    except BaseException:
        shutil.rmtree(temporary);raise
    return summary


def main():
    parser=argparse.ArgumentParser(description='Aura Backtest Lab 1.0 · OFFLINE ONLY')
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--protocol',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        r=run(args.manifest,args.protocol,args.output)
    except (ValueError,KeyError,TypeError,OSError) as error:
        # Local errors only; never dump external bodies, env or secrets.
        print(json.dumps({'status':'BLOCKED','code':str(error) if isinstance(error,ValueError) else type(error).__name__}));raise SystemExit(2)
    print(json.dumps({'status':'REPLAY_COMPLETED','verdict':r['verdict'],'signals':r['signals'],'config_hash':r['config_hash']}))

if __name__=='__main__':main()

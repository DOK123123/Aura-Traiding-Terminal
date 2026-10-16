"""Offline alignment examples using the existing exact production replay adapter.

Consumes a validated local Binance CSV; no Service, ledger, credentials or HTTP.
Native/cache equality and future perturbation are checked on reported examples.
"""
import argparse
from bisect import bisect_left
from collections import Counter
from dataclasses import replace
from datetime import datetime,timezone
import json
from pathlib import Path

from app.lab.local_csv import load_binance_csv
from app.lab.models import canonical
from app.automated.strategy import strategy
from app.automated.engine import DemoError
from scripts.replay_auto42_verification import PrefixCache,snapshot,code_hashes


def diagnose(path: Path, *, stride: int=4) -> dict:
    bars,info=load_binance_csv(path);times=[b.time for b in bars];end=bars[-1].time+900
    # Only exact production rolling windows with all 4160 base warm-up bars.
    first=(bars[0].time+14399)//14400*14400+4160*900
    groups={}
    for at in range(first,end+1,900*stride):groups.setdefault(at//14400*14400,[]).append(at)
    groups.setdefault(end//14400*14400,[])
    if end not in groups[end//14400*14400]:groups[end//14400*14400].append(end)
    passed=[];failed=[];counts=Counter();last=None;checked=0
    for boundary,cutoffs in groups.items():
        start=boundary-4160*900;left=bisect_left(times,start)
        full=bars[left:bisect_left(times,max(cutoffs))]
        if not full or full[0].time!=start:continue
        cache=PrefixCache(full)
        for at in cutoffs:
            window=full[:bisect_left(times,at)-left]
            try:
                with cache.installed():value=snapshot(window,at);decision=strategy(value,window,at+30)
            except DemoError as exc:counts[exc.code]+=1;continue
            evidence=decision['timeframe_alignment'];counts[decision['reason']]+=1
            is_pass=evidence['actual_condition'];target=passed if is_pass else failed
            if len(target)<3 or at==end:
                native=snapshot(window,at)
                if native!=value or strategy(native,window,at+30)!=decision:raise ValueError('NATIVE_REPLAY_MISMATCH')
                # Build a fresh cache including deliberately altered future bars.
                future=[replace(b,open=b.open*2,close=b.close*2,high=b.high*2,low=b.low*2) for b in bars[bisect_left(times,at):bisect_left(times,at)+8]]
                with PrefixCache(window+future).installed():
                    if snapshot(window,at)!=native:raise ValueError('FUTURE_LEAK')
                checked+=1
                example=dict(utc=datetime.fromtimestamp(at,timezone.utc).isoformat(),
                    direction=decision['direction'],reason=decision['reason'],snapshot=evidence,
                    native_replay_equal=True,future_perturbation_invariant=True)
                if len(target)<3:target.append(example)
                if at==end:last=example
    return dict(evidence_type='HISTORICAL_RECONSTRUCTION_NOT_CAPTURED_PRODUCTION',
        source={k:v for k,v in info.items() if k!='path'},sample_stride_15m=stride,
        code_hashes=code_hashes(),counts=dict(counts),passing_examples=passed,failing_examples=failed,
        native_equivalence_cases=checked,last_cutoff=last,
        live_autonomy='NOT_TESTED',orders_submitted=0,
        limitations=['Sampled historical alignment passes are not entry signals.',
            'No access to original production snapshot or deployed commit: reconstruction is conditional.',
            'Replay freshness is evaluated at historical cutoff, not current delivery freshness.'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--csv',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--stride',type=int,choices=(1,4,16),default=4)
    args=p.parse_args();result=diagnose(args.csv,stride=args.stride)
    args.output.write_bytes(canonical(result))
    print(json.dumps(dict(passes=len(result['passing_examples']),failures=len(result['failing_examples']),
        counts=result['counts'],native_equivalence_cases=result['native_equivalence_cases'])))


if __name__=='__main__':main()

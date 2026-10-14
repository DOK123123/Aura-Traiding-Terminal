"""Proper descriptive forward scores; overlapping observations are not independent."""
from collections import defaultdict
from math import log,sqrt,isfinite
from statistics import mean
from .models import verify,STEPS,HORIZONS

BASELINES=('aura','unconditional','same_regime','simple_trend','no_change')


def score(forecast,actual):
    p=forecast.get('probabilities');m=forecast.get('mean_return_pct')
    if type(m) not in (int,float) or not isfinite(m) or not isinstance(p,list) or len(p)!=3 or any(type(x) not in (float,int) or not 0<=x<=1 for x in p) or abs(sum(p)-1)>1e-9:
        return None
    sign=1 if actual>0 else -1 if actual<0 else 0;category=sign+1
    predicted=1 if m>0 else -1 if m<0 else 0
    return dict(absolute_error=abs(actual-m),squared_error=(actual-m)**2,direction=sign,
        direction_correct=predicted==sign,prob_up=p[2],actual_up=int(sign==1),
        brier=sum((v-int(j==category))**2 for j,v in enumerate(p)),
        log_loss=-log(p[category]) if p[category]>0 else None,log_loss_infinite=p[category]==0)


def aggregate(rows):
    if not rows:return dict(count=0,mae=None,rmse=None,directional_accuracy=None,balanced_accuracy=None,brier=None,log_loss=None,calibration=[])
    positives=[x for x in rows if x['direction']==1];negatives=[x for x in rows if x['direction']==-1]
    bins=[]
    for i in range(10):
        points=[x for x in rows if min(9,int(x['prob_up']*10))==i]
        if points:bins.append(dict(bin=i,count=len(points),mean_predicted_up=mean(x['prob_up'] for x in points),observed_up=mean(x['actual_up'] for x in points)))
    infinite=sum(x['log_loss_infinite'] for x in rows)
    return dict(count=len(rows),mae=mean(x['absolute_error'] for x in rows),rmse=sqrt(mean(x['squared_error'] for x in rows)),
        directional_accuracy=mean(x['direction_correct'] for x in rows),
        balanced_accuracy=(mean(x['direction_correct'] for x in positives)+mean(x['direction_correct'] for x in negatives))/2 if positives and negatives else None,
        brier=mean(x['brier'] for x in rows),log_loss=None if infinite else mean(x['log_loss'] for x in rows),
        infinite_log_loss_count=infinite,log_loss_status='INFINITY' if infinite else 'FINITE',calibration=bins,
        balanced_accuracy_note='Binary UP/DOWN recall average, actual zero excluded; neutral mean forecast is wrong for nonzero direction.')


def summarize(records,*,partial=True):
    preds={};outcomes=[];corrected=set()
    for row in records:
        p=verify(row)
        if row['kind']=='PRED':preds[row['id']]=p
        elif row['kind']=='OUTCOME':outcomes.append(p)
        elif row['kind']=='CORRECTION':corrected.add(p['prediction_id'])
    groups=defaultdict(list);invalid=0;pending=4*len(preds)-len([o for o in outcomes if o['prediction_id'] in preds])
    for o in outcomes:
        p=preds.get(o['prediction_id'])
        if p is None:continue
        key=(p['cohort'],p['timeframe'],o['horizon'],p['regime'])
        groups[key].append((p,o))
    results=[]
    # Scores are reported both per regime and across regimes, never pooled across cohorts.
    pooled=defaultdict(list)
    for (cohort,tf,h,regime),pairs in groups.items():pooled[(cohort,tf,h,'ALL')].extend(pairs)
    groups.update(pooled)
    for (cohort,tf,h,regime),pairs in sorted(groups.items()):
        scored={k:[] for k in BASELINES};usable_times=[];eligible=0;abstained=0;bad=0
        for p,o in pairs:
            if o['quality']!='COMPLETE' or p['id'] in corrected:bad+=1;continue
            eligible+=1
            if p['status']!='FORECAST':abstained+=1;continue
            actual=float(o['return_pct'])
            for name,f in [('aura',p['forecasts'][str(h)]),*p['baselines'][str(h)].items()]:
                result=score(f,actual)
                if result:scored[name].append(result)
            usable_times.append(p['closed_at'])
        non_overlap=[]
        for at in sorted(set(usable_times)):
            if not non_overlap or at-non_overlap[-1]>=h*STEPS[tf]:non_overlap.append(at)
        results.append(dict(cohort=cohort,timeframe=tf,horizon=h,regime=regime,
            observed=len(pairs),valid_outcomes=eligible,abstentions=abstained,invalid_or_corrected=bad,
            prediction_coverage=(eligible-abstained)/eligible if eligible else None,
            abstention_rate=abstained/eligible if eligible else None,
            scores={k:aggregate(v) for k,v in scored.items()},non_overlapping_outcome_count=len(non_overlap),
            effective_independent_sample_size=None,confidence_intervals=None,uncertainty='UNKNOWN',
            uncertainty_reason='Serially dependent, overlapping conditional forecasts; no independently established effective N/CI.',
            status='FORWARD_VALIDATION_REQUIRED',partial_sample=partial))
    return dict(status='ПРОВЕРКА ЕЩЁ НЕ ЗАВЕРШЕНА' if not any(g['scores']['aura']['count'] for g in results) else 'DESCRIPTIVE_FORWARD_SCORES',
        predictions_in_sample=len(preds),outcomes_in_sample=len(outcomes),pending_in_sample=max(0,pending),
        corrected_predictions=len(corrected),partial_sample=partial,groups=results,
        edge_status='NOT_ESTABLISHED',multiple_comparisons='3 TF × 4 horizons × 4 baselines plus regime/cohort views; no inferential edge acceptance.',
        interpretation='Proper scores describe recorded forecasts only. Accuracy is not profitability. No iid confidence interval is claimed.')

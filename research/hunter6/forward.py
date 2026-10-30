"""Reproduce exported live inputs offline; never qualify an edge or alter registry."""
from app.hunter.engine import FAMILIES, Prepared
from app.hunter.market import LIVE_INPUT_CONTRACT, LIVE_WINDOW, SOURCE, STEPS, fresh_quote, validate_bars
from app.hunter.store import MODEL_HASH, evidence_hash


def audit_page(page: dict) -> dict:
    """Verify one bounded owner export. Hash integrity is not source authenticity."""
    if (page.get('scope')!='AURA6_PARSED_NATIVE_INPUTS_NOT_PROFIT_PROOF'
            or page.get('frame') not in STEPS or not isinstance(page.get('items'),list)
            or len(page['items'])>100):
        raise ValueError('INVALID_INPUT_EXPORT')
    frame=page['frame'];step=STEPS[frame];previous_seq=0;previous_cutoff=None
    gaps=[];technical=0;watch=0
    for item in page['items']:
        payload=item['payload'];snap=payload['snapshot'];rows=snap['bars'];at=payload['detected_at']
        if item['sha256']!=evidence_hash(payload):raise ValueError('INPUT_HASH_MISMATCH')
        if payload['model_sha256']!=MODEL_HASH or payload['input_contract']!=LIVE_INPUT_CONTRACT:
            raise ValueError('INPUT_MODEL_OR_CONTRACT_MISMATCH')
        if (snap['source']!=SOURCE or snap['frame']!=frame or snap['step']!=step
                or len(rows)!=LIVE_WINDOW or not fresh_quote(snap['quote'],at)):
            raise ValueError('UNVERIFIED_INPUT_SNAPSHOT')
        validate_bars(rows,step)
        cutoff=rows[-1][0]+step
        if cutoff!=int(at//step)*step:raise ValueError('INPUT_CUTOFF_MISMATCH')
        if type(item['seq']) is not int or item['seq']<=previous_seq or previous_cutoff is not None and cutoff<=previous_cutoff:
            raise ValueError('DUPLICATE_OR_UNORDERED_INPUT')
        if previous_cutoff is not None and cutoff!=previous_cutoff+step:
            gaps.append({'after':previous_cutoff,'before':cutoff,'missing_cutoffs':(cutoff-previous_cutoff)//step-1})
        prepared=Prepared(rows,frame);plans=[]
        for family in FAMILIES:
            plans.extend(prepared.plans(len(rows)-1,family,cutoff=cutoff,watch=True))
        if plans!=payload['plans']:raise ValueError('LIVE_PLAN_REPRODUCTION_MISMATCH')
        technical+=sum(p['technical_trigger'] for p in plans)
        watch+=sum(not p['technical_trigger'] for p in plans)
        previous_seq=item['seq'];previous_cutoff=cutoff
    return {'scope':'INPUT_REPRODUCTION_ONLY','frame':frame,'inputs_verified':len(page['items']),
            'technical_plans':technical,'preparation_plans':watch,'internal_gaps':gaps,
            'has_more':page['has_more'],'earliest_retained_seq':page['earliest_retained_seq'],
            'model_sha256':MODEL_HASH,'input_contract':LIVE_INPUT_CONTRACT,
            'source_authenticity_verified':False,'complete_history_claimed':False,
            'profitability_evaluated':False,'approved_for_confirmed':[]}

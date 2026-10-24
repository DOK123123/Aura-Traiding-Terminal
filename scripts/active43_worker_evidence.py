"""Value-free Cloudflare comparison evidence. Never an equality relaxation."""

# Only schema field names may appear in output. Unknown response keys might
# themselves contain credentials: describe those by ordinal, never repr/key/hash.
import math

FIELDS=frozenset(('bindings','name','type','text','json','namespace_id','id','service','environment',
    'compatibility_date','compatibility_flags','limits','cpu_ms','usage_model','script_runtime',
    'observability','enabled','head_sampling_rate','logs','invocation_logs','logpush','tail_consumers',
    'placement','mode','migration_tag','annotations','workers/commit_sha','workers/message',
    'workers/tag','main_module','body_part','tags','schedules','cron','created_on','modified_on',
    'previews_enabled','exports','default','cache','cross_version_cache','state','resources','script',
    'etag','handlers','last_deployed_from','metadata','source','number'))
MISSING=object()


def kind(value):
    if value is MISSING:return 'missing'
    if value is None:return 'null'
    if type(value) is bool:return 'boolean'
    if type(value) in (int,float):return 'number'
    if isinstance(value,str):return 'string'
    if isinstance(value,list):return 'array'
    if isinstance(value,dict):return 'object'
    return 'invalid'


def equivalent(left,right):
    """JSON semantics: object order irrelevant, booleans never equal numbers."""
    if kind(left)!=kind(right):return False
    if isinstance(left,dict):return left.keys()==right.keys() and all(equivalent(left[k],right[k]) for k in left)
    if isinstance(left,list):return len(left)==len(right) and all(equivalent(a,b) for a,b in zip(left,right))
    if kind(left)=='number':return math.isfinite(left) and math.isfinite(right) and left==right
    return left==right


def differences(before,after,limit=64):
    """Return paths/change kinds/types only. No values, lengths or fingerprints."""
    changes=[];truncated=False
    def add(path,left,right):
        nonlocal truncated
        if len(changes)>=limit:truncated=True;return
        changes.append(dict(path=path,before_type=kind(left),after_type=kind(right),
                            change='missing_or_added' if left is MISSING or right is MISSING else 'different'))
    def walk(left,right,path,depth=0):
        nonlocal truncated
        if equivalent(left,right):return
        if len(changes)>=limit:truncated=True;return
        if depth>=12:add(path,left,right);return
        if isinstance(left,dict) and isinstance(right,dict):
            keys=sorted(set(left)|set(right),key=lambda x:str(x))
            for index,key in enumerate(keys):
                label=key if isinstance(key,str) and key in FIELDS else 'unknown_field_'+str(index)
                walk(left.get(key,MISSING),right.get(key,MISSING),path+'.'+label,depth+1)
        elif isinstance(left,list) and isinstance(right,list):
            for index in range(min(max(len(left),len(right)),256)):
                walk(left[index] if index<len(left) else MISSING,
                     right[index] if index<len(right) else MISSING,path+'['+str(index)+']',depth+1)
            if max(len(left),len(right))>256:truncated=True
        else:add(path,left,right)
    walk(before,after,'$')
    return dict(equal=equivalent(before,after),changes=changes,truncated=truncated,values_redacted=True)

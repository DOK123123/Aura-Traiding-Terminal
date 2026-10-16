"""Versioned bounded manifests and independent compressed array chunks."""
from copy import deepcopy
import gzip
import hashlib
import json
import re
from app.lab.models import LabError,canonical,digest

FORMAT='AURA_RESEARCH_CHUNKED_2'
COMPACT_LIMIT=512*1024
CHUNK_LIMIT=128*1024
RECORD_LIMIT=64*1024
TOTAL_LIMIT=128*1024*1024
ARRAYS=('decisions','trades','equity_curve','daily_equity')
STATES=('REJECTED','NEEDS_VALIDATION')


def bad():raise LabError('RESEARCH_INTEGRITY')

def decode(raw):
    try:return json.loads(raw,parse_constant=lambda value:bad())
    except (ValueError,TypeError,UnicodeError):bad()

def streamed_digest(value):
    h=hashlib.sha256()
    for part in json.JSONEncoder(sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).iterencode(value):h.update(part.encode())
    return h.hexdigest()


def validate_report(value):
    if type(value) is not dict or value.get('research_only') is not True or value.get('activation_available') is not False or value.get('final_test_is_independent') is not False:bad()
    if type(value.get('auditor')) is not dict or value['auditor'].get('status') not in STATES:bad()
    if type(value.get('runs')) is not list or len(value['runs'])>32:bad()
    if type(value.get('config')) is not dict or value.get('config_hash')!=digest(value['config']):bad()
    for run in value['runs']:
        if type(run) is not dict or type(run.get('split')) is not str or type(run.get('scale')) is not str:bad()


def split_report(report,emit):
    """emit(run_key,kind,ordinal,start,count,raw)->descriptor; transaction owned by Store."""
    validate_report(report)
    original=dict(report);checksum=original.pop('checksum',None)
    if checksum!=streamed_digest(original):bad()
    result={k:v for k,v in original.items() if k!='runs'};runs=[];total=0;chunks=0
    for index,run in enumerate(original['runs']):
        compact={k:v for k,v in run.items() if k not in ARRAYS};compact['run_key']=str(index);refs={}
        for kind in ARRAYS:
            values=run.get(kind,[])
            if type(values) is not list or len(values)>100000:bad()
            descriptors=[];pending=[];size=0;start=0;h=hashlib.sha256()
            def flush():
                nonlocal start,pending,size,chunks
                if not pending:return
                raw=b''.join(pending);descriptors.append(emit(str(index),kind,len(descriptors),start,len(pending),raw))
                start+=len(pending);pending=[];size=0;chunks+=1
                if chunks>2048:raise LabError('RESULT_LIMIT')
            for record in values:
                if type(record) is not dict:bad()
                raw=canonical(record)+b'\n'
                if len(raw)>RECORD_LIMIT:raise LabError('RESULT_LIMIT')
                if pending and (size+len(raw)>CHUNK_LIMIT or len(pending)>=256):flush()
                total+=len(raw)
                if total>TOTAL_LIMIT:raise LabError('RESULT_LIMIT')
                h.update(raw);pending.append(raw);size+=len(raw)
            flush()
            refs[kind]=dict(records=len(values),sha256=h.hexdigest(),chunks=descriptors)
        compact['artifacts']=refs;runs.append(compact)
    result.update(runs=runs,storage_format=FORMAT,logical_report_checksum=checksum)
    result['checksum']=streamed_digest(result)
    if len(canonical(result))>COMPACT_LIMIT:raise LabError('RESULT_LIMIT')
    return result


def checked_manifest(value):
    validate_report(value)
    copy=dict(value);checksum=copy.pop('checksum',None)
    if copy.get('storage_format')!=FORMAT or checksum!=streamed_digest(copy):bad()
    if not re.fullmatch('[0-9a-f]{64}',str(copy.get('logical_report_checksum',''))):bad()
    for index,run in enumerate(copy['runs']):
        if run.get('run_key')!=str(index) or type(run.get('artifacts')) is not dict or set(run['artifacts'])!=set(ARRAYS):bad()
        for ref in run['artifacts'].values():
            if type(ref) is not dict or not re.fullmatch('[0-9a-f]{64}',str(ref.get('sha256',''))) or type(ref.get('records')) is not int or not 0<=ref['records']<=100000 or type(ref.get('chunks')) is not list:bad()
            at=0
            for ordinal,d in enumerate(ref['chunks']):
                if type(d) is not dict or d.get('ordinal')!=ordinal or d.get('start')!=at or type(d.get('count')) is not int or not 1<=d['count']<=256:bad()
                if type(d.get('bytes')) is not int or not 0<d['bytes']<=CHUNK_LIMIT or not re.fullmatch('[0-9a-f]{64}',str(d.get('sha256',''))):bad()
                at+=d['count']
            if at!=ref['records']:bad()
    return value


def unpack_chunk(blob,descriptor):
    import io
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:raw=stream.read(CHUNK_LIMIT+1)
        if len(raw)!=descriptor['bytes'] or hashlib.sha256(raw).hexdigest()!=descriptor['sha256']:bad()
        values=[decode(line) for line in raw.splitlines()]
        if len(values)!=descriptor['count'] or any(type(v) is not dict for v in values):bad()
        return values
    except (OSError,EOFError,TypeError):bad()

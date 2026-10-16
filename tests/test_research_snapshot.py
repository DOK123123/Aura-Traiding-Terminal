"""Offline snapshot transport, integrity, access and production isolation."""
import asyncio
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import httpx
import pytest
from app.lab.models import LabError, canonical, digest
from app.research.storage import Store
from app.research.snapshot import SnapshotStore, export_snapshot, publish_snapshot, public_data, INDEX_LIMIT, PACKED_LIMIT
from app.research.experiment import frozen_config
from app.research.data import available
from tests.test_research_release_blockers import synthetic_report

@pytest.fixture
def sample(tmp_path):
    store=Store(tmp_path/'store'); cfg=frozen_config('MEAN_REVERSION',available()); ident=store.enqueue(cfg)
    claim=store.claim(ident); report=synthetic_report(cfg,300); report['llm_used']=False; report.pop('checksum'); report['checksum']=digest(report); store.finish(ident,report,attempt=claim['attempt'])
    return store,ident,report


def test_exact_export_restart_pages_and_no_database_or_calls(sample,tmp_path):
    s,i,r=sample; s.reserve('openai','DUMMY_PRIVATE_MODEL',1,10,10)
    out=tmp_path/'bundle'; result=export_snapshot(s,i,out)
    before={f.name:f.read_bytes() for f in out.iterdir()}
    fresh=SnapshotStore(out); assert fresh.verify()['checksum']==result['checksum']
    assert fresh.calls()==[] and all(not f.name.endswith(('.sqlite3','.db')) for f in out.iterdir())
    assert b'DUMMY_PRIVATE_MODEL' not in b''.join(before.values())
    assert fresh.get(i)['report']==s.get(i)['report']
    for k in ('decisions','trades','equity_curve','daily_equity'):
        at=0; records=[]
        while True:
            p=fresh.page(i,'0',k,at,100); records+=p['records']
            if p['next_offset'] is None:break
            at=p['next_offset']
        assert records==r['runs'][0][k]
    assert before=={f.name:f.read_bytes() for f in out.iterdir()}
    with pytest.raises(LabError,match='RESEARCH_ALREADY_PROCESSED'):export_snapshot(s,i,out)


def test_atomic_bad_chunk_export_leaves_no_destination(sample,tmp_path):
    s,i,r=sample
    with s.connect() as c:c.execute('update chunks set payload=?',(b'bad',))
    with pytest.raises(LabError):export_snapshot(s,i,tmp_path/'bundle')
    assert not (tmp_path/'bundle').exists()


@pytest.mark.parametrize('damage',['checksum','type','chunk','missing','extra','symlink','oversized','bomb','deflate'])
def test_corrupted_snapshot_is_rejected(sample,tmp_path,damage):
    s,i,_=sample; out=tmp_path/'bundle'; export_snapshot(s,i,out)
    f=out/'index.json'; chunks=sorted(out.glob('chunk-*'))
    if damage=='checksum': f.write_bytes(f.read_bytes().replace(b'MEAN_REVERSION',b'MEAN_REVERSIOX',1))
    elif damage=='type': f.write_bytes(b'[]')
    elif damage=='chunk': chunks[0].write_bytes(b'bad')
    elif damage=='missing': chunks[0].unlink()
    elif damage=='extra': (out/'unapproved.sql').write_text('NO_SQL_EXECUTION')
    elif damage=='symlink':
        saved=tmp_path/'outside'; chunks[0].rename(saved); chunks[0].symlink_to(saved)
    elif damage=='oversized': f.write_bytes(b' '* (INDEX_LIMIT+1))
    elif damage=='deflate':
        import gzip
        b=gzip.compress(b'{}\n'); chunks[0].write_bytes(b[:10]+b'\xff'*20+b[-8:])
    else:
        import gzip
        chunks[0].write_bytes(gzip.compress(b'A'*2**20))
    with pytest.raises(LabError):SnapshotStore(out).verify()


@pytest.mark.parametrize('payload',[{'api_key':'DUMMY'}, {'nested':{'password':'DUMMY'}}, {'x':'Bearer DUMMY_DONT_EXPOSE'}, {'x':'sk-DUMMY1234567890123'}, {'x':'https://owner:password@example.invalid'}])
def test_secret_bearing_metadata_rejected(payload):
    with pytest.raises(LabError):public_data(payload)


def test_publish_requires_expected_checksum_and_no_overwrite(sample,tmp_path):
    s,i,_=sample; bundle=tmp_path/'bundle'; export_snapshot(s,i,bundle); approved=tmp_path/'checkout/docs/research-snapshot'; approved.parent.mkdir(parents=True)
    with patch('app.research.snapshot.APPROVED',approved):
        with pytest.raises(LabError):publish_snapshot(bundle,'0'*64)
        checksum=SnapshotStore(bundle).index['checksum'];publish_snapshot(bundle,checksum)
        assert SnapshotStore(approved).get(i)['report']==s.get(i)['report']
        before={f.name:f.read_bytes() for f in approved.iterdir()}
        with pytest.raises(LabError,match='RESEARCH_ALREADY_PROCESSED'):publish_snapshot(bundle,checksum)
        assert before=={f.name:f.read_bytes() for f in approved.iterdir()}
        with patch.dict('os.environ',RENDER='true'):
            with pytest.raises(LabError):publish_snapshot(bundle,checksum)


def test_offline_cli_owner_and_approval_required(tmp_path):
    from scripts.research_snapshot import main
    args=['publish','--bundle',str(tmp_path),'--checksum','0'*64]
    with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_SNAPSHOT'),patch('getpass.getpass',return_value='wrong'),patch('scripts.research_snapshot.publish_snapshot',side_effect=AssertionError('NO_PUBLISH')):
        assert main(args)==1
    with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_SNAPSHOT'),patch('getpass.getpass',return_value='DUMMY_OWNER_SNAPSHOT'),patch('scripts.research_snapshot.publish_snapshot',side_effect=AssertionError('NO_APPROVAL')):
        assert main(args)==1


def test_actual_terminal_viewer_snapshot_owner_read_only_no_execution(sample,tmp_path):
    from app.main import app
    from app.research.api import service
    s,i,_=sample; bundle=tmp_path/'bundle'; export_snapshot(s,i,bundle)
    async def work():
        with patch.dict('os.environ',AURA_RESEARCH_STATE_DIR='',AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_SNAPSHOT'),patch('app.research.snapshot.APPROVED',bundle),patch('app.research.experiment.execute',side_effect=AssertionError('NO_EXECUTION')),patch('subprocess.Popen',side_effect=AssertionError('NO_SPAWN')):
            service.cache_clear()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://offline.invalid') as c:
                assert (await c.get('/api/research')).status_code==401
                c.auth=('aura','DUMMY_OWNER_SNAPSHOT')
                r=await c.get('/api/research');assert r.status_code==200 and r.json()['writable'] is False and r.json()['llm']['status']=='AI_NOT_CONFIGURED'
                assert (await c.get(f'/api/research/experiments/{i}/records?run_key=0')).status_code==200
                for path in ('/api/research/queue',f'/api/research/queue/{i}/run','/api/research/ideas'):
                    r=await c.post(path,headers={'X-Aura-Lab':'research-only'},json={'hypothesis':'MEAN_REVERSION'} if path.endswith('/queue') else {})
                    assert r.status_code==403
                assert (await c.post('/api/research/import')).status_code in (404,405)
                assert (await c.get('/api/health')).status_code==200
                chunk=next(bundle.glob('chunk-0-decisions-*'));chunk.write_bytes(b'bad')
                r=await c.get(f'/api/research/experiments/{i}/records?run_key=0&kind=decisions');assert r.status_code==503
    try:asyncio.run(work())
    finally:service.cache_clear()


def test_corrupt_deflate_is_controlled_http_error(sample,tmp_path):
    import gzip
    from fastapi import FastAPI
    from app.research.api import router,instance
    from app.research.service import Service
    s,i,_=sample; b=gzip.compress(b'{}\n'); bad=b[:10]+b'\xff'*20+b[-8:]
    with s.connect() as c:c.execute("update chunks set payload=? where kind='decisions'",(bad,))
    app=FastAPI();app.include_router(router);app.dependency_overrides[instance]=lambda:Service(tmp_path,store=s)
    async def work():
        with patch.dict('os.environ',AURA_TESTNET_VIEW_PASSWORD='DUMMY_OWNER_SNAPSHOT'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://offline.invalid',auth=('aura','DUMMY_OWNER_SNAPSHOT')) as c:
                r=await c.get(f'/api/research/experiments/{i}/records?run_key=0&kind=decisions')
                assert r.status_code==503 and r.json()['code']=='RESEARCH_INTEGRITY'
    asyncio.run(work())

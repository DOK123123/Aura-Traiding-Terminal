"""Explicit external durable state. No ephemeral fallback, no trading DB migration."""
import json
import os
from pathlib import Path
import tempfile
import uuid
from app.lab.models import LabError,canonical
from .storage import Store

ROOT=Path(__file__).resolve().parents[2]
MARKER='aura-research-storage.json'

def location(value:str|Path) -> Path:
    raw=Path(value).expanduser()
    if not raw.is_absolute():raise LabError('RESEARCH_DURABLE_PATH_REQUIRED')
    if any(p.is_symlink() for p in (raw,*raw.parents)):raise LabError('RESEARCH_STORAGE_CONFLICT')
    p=raw.resolve()
    forbidden=(ROOT,Path('/tmp'),Path('/var/tmp'),Path('/dev/shm'),Path(tempfile.gettempdir()).resolve(),Path('/proc'),Path('/sys'),Path('/dev'))
    if p==Path('/') or any(p==f or f in p.parents for f in forbidden):raise LabError('RESEARCH_DURABLE_PATH_REQUIRED')
    return p


def initialize(value:str|Path) -> Path:
    p=location(value)
    if p.exists() and any(p.iterdir()):raise LabError('RESEARCH_STORAGE_CONFLICT')
    p.mkdir(parents=True,exist_ok=True,mode=0o700);p.chmod(0o700)
    marker=dict(format='AURA_RESEARCH_STATE_2',storage_id=uuid.uuid4().hex,
        durability='OPERATOR_SELECTED_PERSISTENT_DIRECTORY; HARDWARE_AND_BACKUP_NOT_ATTESTED')
    with (p/MARKER).open('xb') as f:f.write(canonical(marker))
    Store(ROOT,directory=p)
    return p


def configured_store(*,writable=False,env=None):
    e=os.environ if env is None else env;value=e.get('AURA_RESEARCH_STATE_DIR','')
    if not value:return None
    if e.get('AURA_RESEARCH_STORAGE_MODE')!='durable':raise LabError('RESEARCH_DURABLE_PATH_REQUIRED')
    if writable and e.get('RENDER'):raise LabError('RESEARCH_LOCAL_WORKBENCH_REQUIRED')
    p=location(value)
    try:
        if (p/MARKER).is_symlink() or (p/MARKER).stat().st_nlink!=1:raise ValueError()
        with (p/MARKER).open('rb') as f:raw=f.read(4097)
        marker=json.loads(raw)
        if len(raw)>4096 or type(marker) is not dict or marker.get('format')!='AURA_RESEARCH_STATE_2':raise ValueError()
    except (OSError,ValueError):raise LabError('RESEARCH_STORAGE_NOT_CONFIGURED') from None
    return Store(ROOT,directory=p,readonly=not writable)

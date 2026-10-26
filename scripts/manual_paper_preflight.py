"""Read-only runtime preflight. Never seeds a ledger or touches Active43.

Run after an explicitly authorized deployment: python -m scripts.manual_paper_preflight
Outputs only safe configuration metadata and public quote status, never secrets.
"""
import asyncio
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote

import httpx

from app.manual_paper.bitget import fetch_execution_quote
from app.manual_paper.store import ManualStore


def storage_check(env=None):
    env=os.environ if env is None else env
    raw=env.get('AURA_MANUAL_PAPER_DB','')
    path=Path(raw)
    mount=Path(env.get('AURA_MANUAL_PAPER_MOUNT','/var/data'))
    enabled=env.get('AURA_MANUAL_PAPER_ENABLED','').lower()=='true'
    password=env.get('AURA_TESTNET_VIEW_PASSWORD','')
    mode=env.get('AURA_MANUAL_PAPER_STORAGE','')
    valid_path=bool(raw and path.is_absolute() and path.name=='manual-paper.sqlite3' and path.parent.is_dir() and not path.is_symlink())
    mounted=bool(mount.is_absolute() and mount!=Path('/') and mount.resolve()==mount and os.path.ismount(mount))
    confined=bool(valid_path and mounted and path.resolve().is_relative_to(mount))
    writable=bool(valid_path and os.access(path if path.exists() else path.parent,os.W_OK))
    result=dict(virtual_only=True,exchange_execution=False,enabled=enabled,
                owner_password_configured=len(password)>=12,storage_mode=mode,
                persistent_mount_verified=mounted,path_confined=confined,write_permission_verified=writable,
                database_exists=bool(valid_path and path.is_file()),journal_read_verified=False,
                ready=False,code='CONFIGURATION_INCOMPLETE')
    if not (enabled and len(password)>=12 and mode=='persistent-disk' and confined and writable):
        return result
    result.update(ready=True,code='READY_EMPTY_DATABASE_NOT_INITIALIZED')
    if not path.is_file():
        return result
    db=None
    try:
        # URI mode=ro avoids all schema creation, WAL setup and account seeding.
        db=sqlite3.connect('file:'+quote(str(path))+'?mode=ro',uri=True,timeout=3)
        db.execute('PRAGMA query_only=ON')
        tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables!={'state','requests'}:
            raise ValueError('STORAGE_SCOPE_MISMATCH')
        if db.execute('PRAGMA quick_check').fetchone()!=('ok',):
            raise ValueError('CORRUPT_JOURNAL')
        row=db.execute('SELECT data,version FROM state WHERE id=1').fetchone()
        if row is None:
            if db.execute('SELECT 1 FROM requests LIMIT 1').fetchone():
                raise ValueError('CORRUPT_JOURNAL')
        else:
            ManualStore.decode(row[0])
            if type(row[1]) is not int or row[1]<1:
                raise ValueError('CORRUPT_JOURNAL')
            result.update(journal_read_verified=True,version=row[1],code='READY_EXISTING_JOURNAL')
        return result
    except (sqlite3.Error,ValueError,TypeError,OSError):
        result.update(ready=False,code='JOURNAL_READ_FAILED')
        return result
    finally:
        if db is not None:db.close()


async def preflight(client=None,env=None):
    result=storage_check(env)
    async def check(c):
        try:
            q=await fetch_execution_quote(c)
            # Public quote metadata only; the full market book is unnecessary.
            return dict(ready=True,source=q['source'],symbol=q['symbol'],product=q['product'],quote_time=q['time'])
        except ValueError:
            return dict(ready=False,code='BITGET_QUOTE_UNAVAILABLE')
    if client is None:
        async with httpx.AsyncClient(follow_redirects=False,timeout=8) as c:
            result['market']=await check(c)
    else:
        result['market']=await check(client)
    result['launch_ready']=result['ready'] and result['market']['ready']
    return result


def main():
    result=asyncio.run(preflight())
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0 if result['launch_ready'] else 1


if __name__=='__main__':
    raise SystemExit(main())

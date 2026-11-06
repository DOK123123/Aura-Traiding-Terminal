"""Proposed schema tested ONLY in a disposable network=none PostgreSQL."""
import json
import os
from pathlib import Path
import uuid
import pytest
from scripts.verify_manual_paper_postgres import PG, wait, DATABASE
from scripts.verify_practice_postgres import docker, IMAGE
from scripts.build_manual_preview_sql import rendered


@pytest.mark.skipif(os.getenv('AURA_MANUAL_PAPER_VERIFY_POSTGRES') != 'true',
                    reason='Disposable PostgreSQL opt-in required')
def test_signal_state_cas_roles_restart_and_existing_guard(monkeypatch):
    if os.getenv('RENDER'):
        raise ValueError('LOCAL_DISPOSABLE_ONLY')
    name = 'aura-manual-pg-' + uuid.uuid4().hex[:12]
    docker('run', '-d', '--name', name, '--label', 'aura.manual.verification=true',
           '--network', 'none', '--memory', '512m', '--cpus', '1',
           '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_DB=' + DATABASE, IMAGE)
    try:
        wait(name)
        pg = PG(name)
        pg.sql('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;')
        pg.sql(rendered('abcdefghijklmnopqrst'))
        root = Path(__file__).resolve().parents[1]
        sql = (root / 'deploy/manual-preview/signal-lock-schema.sql').read_text()
        failed = pg.sql(sql, check=False)
        assert failed.returncode != 0 and 'DEDICATED_PREVIEW_SCOPE_REQUIRED' in failed.stderr
        assert pg.sql("SELECT to_regnamespace('aura_preview_signals') IS NULL;") == 't'
        pg.sql("UPDATE public.aura_manual_preview_scope SET project_ref='kkxdftdojvnsjqlrulpb';")
        paper = pg.sql('SELECT payload FROM public.aura_manual_paper_v1_account;')
        guard = pg.sql("SELECT pg_get_functiondef('public.aura_manual_preview_guard()'::regprocedure);")
        pg.sql(sql)
        pg.sql(sql)
        assert pg.sql('SELECT payload FROM public.aura_manual_paper_v1_account;') == paper
        assert pg.sql("SELECT pg_get_functiondef('public.aura_manual_preview_guard()'::regprocedure);") == guard
        for role in ['anon', 'authenticated']:
            for request in ['SELECT public.aura_preview_lock_load_v1();',
                            'SELECT * FROM aura_preview_signals.lock_state_v1;']:
                result = pg.sql(request, role=role, check=False)
                assert result.returncode != 0 and 'permission denied' in result.stderr.lower()
        claims = '{"role":"service_role"}'
        assert json.loads(pg.sql("SET request.jwt.claims='" + claims + "'; SELECT public.aura_manual_preview_guard();", role='service_role'))['isolated'] is True
        state = {'events': {'stable-id': {'status': 'CANDIDATE'}}, 'notices': {}, 'cooldowns': {}}
        call = "SELECT public.aura_preview_lock_commit_v1(0,'" + json.dumps(state) + "'::jsonb);"
        assert pg.sql(call, role='service_role') == 't'
        assert pg.sql(call, role='service_role') == 'f'  # conflicting process cannot overwrite
        pg.restart()
        value = json.loads(pg.sql('SELECT public.aura_preview_lock_load_v1();', role='service_role'))
        assert value == {'version': 1, 'state': state}
        for invalid in ['null', '{}', '{"events":{},"notices":{},"cooldowns":null}']:
            result = pg.sql("SELECT public.aura_preview_lock_commit_v1(1,'" + invalid + "'::jsonb);", role='service_role', check=False)
            assert result.returncode != 0 and 'LOCK_STATE_FORMAT' in result.stderr
        assert json.loads(pg.sql('SELECT public.aura_preview_lock_load_v1();', role='service_role')) == value
    finally:
        docker('rm', '-fv', name, check=False)

"""Real, disposable PostgreSQL verification. Never accepts a URL/DSN or Supabase key.

python -m scripts.verify_practice_postgres --output /tmp/practice-postgres.json
Docker uses its local Unix socket, --network none, no published ports, a temporary
data volume and fixed test database. Quotes are explicitly OFFLINE fixtures.
The production Service/Store validation and execution functions are reused; only
the RPC wire adapter is replaced with real psql calls. This does NOT verify
PostgREST, Supabase hosting, Render or live autonomous execution.
"""
import argparse
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal as D, ROUND_CEILING, ROUND_HALF_EVEN, localcontext
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid

from app.automated.engine import DemoError, initial
from app.automated.storage import packed
from app.practice.core import SOURCE, seed, transition
from app.practice.service import Service
from app.practice.storage import Store

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'postgres:16-bookworm@sha256:0ea6700a3b4f0ae6ce746519073558aed4d88a79d8d07622a9a644946c7319c4'
DATABASE = 'aura_practice_verification'


def docker(*args, input=None, check=True, timeout=60):
    env = dict(os.environ)
    for name in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
        env.pop(name, None)
    return subprocess.run(['docker', '--host=unix:///var/run/docker.sock', *args],
                          input=input, text=True, capture_output=True, env=env,
                          check=check, timeout=timeout)


class PG:
    def __init__(self, container):
        if not re.fullmatch(r'aura-practice-pg-[a-f0-9]{12}', container):
            raise ValueError('Disposable verification container required')
        self.container = container
        identity = json.loads(docker('inspect', '--format',
            '{{json .Config.Labels}}', container).stdout)
        network = docker('inspect', '--format', '{{.HostConfig.NetworkMode}}', container).stdout.strip()
        if identity.get('aura.practice.verification') != 'true' or network != 'none':
            raise ValueError('Unlabelled or network-enabled container forbidden')

    def sql(self, sql, role='postgres', check=True):
        if role not in ('postgres', 'service_role', 'anon', 'authenticated'):
            raise ValueError('Unknown test role')
        result = docker('exec', '-i', self.container, 'psql', '-X', '-qAt',
                        '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', DATABASE,
                        input='SET ROLE ' + role + ';\n' + sql, check=check)
        return result.stdout.strip() if check else result

    def value(self, sql, role='postgres'):
        value = self.sql(sql, role)
        return {'t': True, 'f': False}[value] if value in ('t', 'f') else json.loads(value)

    def rpc(self, name, args, role='service_role'):
        expressions = {
            'aura_practice_load': "a->'seed'",
            'aura_practice_commit': "(a->>'expected_revision')::bigint,a->'new_state',a->'new_events',a->>'operation_key'",
            'aura_practice_history': "a->>'selected_epoch',(a->>'after_seq')::bigint,(a->>'row_limit')::integer,a->>'event_id'",
        }
        encoded = base64.b64encode(json.dumps(args).encode()).decode()
        sql = ("WITH arg AS (SELECT convert_from(decode('" + encoded +
               "','base64'),'UTF8')::jsonb a) SELECT public." + name +
               '(' + expressions[name] + ') FROM arg;')
        return self.value(sql, role)

    def reset_practice(self):
        # This method is confined to the guarded disposable container/test DB.
        self.sql('TRUNCATE public.aura_practice_events,public.aura_practice_account RESTART IDENTITY;')

    def restart(self):
        docker('restart', self.container)
        for _ in range(100):
            if docker('exec', self.container, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres',
                      '-d', DATABASE, check=False).returncode == 0:
                return
            time.sleep(.1)
        raise RuntimeError('Local PostgreSQL did not recover')

    def auto42_snapshot(self):
        dump = docker('exec', self.container, 'pg_dump', '-U', 'postgres', '-d', DATABASE,
                      '--no-owner', '-t', 'public.aura_auto42_*').stdout
        stable = '\n'.join(x for x in dump.splitlines()
                           if not x.startswith(('\\restrict ', '\\unrestrict ', '-- Dumped')))
        functions = self.sql("SELECT coalesce(jsonb_agg(pg_get_functiondef(oid) ORDER BY proname),'[]'::jsonb) "
                             "FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname LIKE 'aura_auto42_%';")
        return hashlib.sha256((stable + functions).encode()).hexdigest()


class PostgreSQLStore(Store):
    """SQL-only adapter, no mocked database or HTTP response."""
    def __init__(self, pg):
        self.pg = pg

    async def rpc(self, name, args):
        value = await asyncio.to_thread(self.pg.rpc, name, args)
        if isinstance(value, dict) and value.get('error'):
            raise DemoError(value['error'])
        return value

    async def close(self):
        pass


class OfflineQuotes:
    def __init__(self):
        self.trade = 0
        self.set('100')

    def set(self, price):
        self.trade += 1
        self.value = dict(price=price, time_ms=int(time.time() * 1000),
                          trade_id=self.trade, source=SOURCE)

    async def get(self):
        return deepcopy(self.value)

    async def close(self):
        pass


def body(side='LONG'):
    return dict(request_id=str(uuid.uuid4()), direction=side, expected_price='100',
                stop_loss='98' if side == 'LONG' else '102',
                take_profit='104' if side == 'LONG' else '96')


def commit_args(env, quote, command, kind='OPEN'):
    state, event = transition(env['state'], quote, int(time.time()), kind, command)
    key = 'practice:cmd:' + command['request_id']
    from app.lab.models import digest
    event.update(id=key, command_id=command['request_id'],
                 command_hash=digest(dict(kind=kind, body=command)))
    return dict(expected_revision=env['revision'], new_state=packed(state),
                new_events=[dict(event, **packed(event))], operation_key=key)


async def verify(pg):
    checks, trades = [], []

    def passed(name, evidence):
        checks.append(dict(name=name, status='PASS', evidence=evidence))

    # Supabase-like prerequisites and deliberately broad default grants, so the
    # migration must remove inherited browser-role access on its new objects.
    pg.sql('CREATE SCHEMA extensions; '
           'CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; '
           'CREATE ROLE service_role NOLOGIN BYPASSRLS; '
           'GRANT USAGE ON SCHEMA public,extensions TO anon,authenticated,service_role; '
           'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon,authenticated,service_role; '
           'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon,authenticated,service_role;')
    pg.sql((ROOT / 'scripts/auto42_schema.sql').read_text())
    auto = packed(initial(int(time.time()), epoch='OFFLINE_AUTO42_UNCHANGED'))
    encoded = base64.b64encode(json.dumps(auto).encode()).decode()
    pg.sql("SELECT public.aura_auto42_load(convert_from(decode('" + encoded + "','base64'),'UTF8')::jsonb);")
    before = pg.auto42_snapshot()
    migration = (ROOT / 'scripts/practice_schema.sql').read_text()
    pg.sql(migration)
    assert pg.auto42_snapshot() == before
    pg.sql(migration)
    assert pg.auto42_snapshot() == before
    passed('migration_and_reapply', 'Both executions succeeded; Auto42 table/data/DDL/function dump hash unchanged')
    assert pg.value("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'aura_practice_%';") == 2
    assert pg.value("SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname LIKE 'aura_practice_%';") == 4
    passed('objects', '2 tables, 3 RPC functions, 1 trigger function created')
    assert pg.value("SELECT bool_and(relrowsecurity) FROM pg_class WHERE oid IN ('aura_practice_account'::regclass,'aura_practice_events'::regclass);")
    assert pg.value("SELECT rolbypassrls AND NOT rolsuper FROM pg_roles WHERE rolname='service_role';")
    store = PostgreSQLStore(pg)
    loaded = await store.load(int(time.time()))
    assert loaded['state']['balance'] == '10000'
    assert await store.history() == []
    passed('service_role_rpc', 'Non-superuser BYPASSRLS role executed load/history through SECURITY DEFINER RPCs')

    for role in ('anon', 'authenticated'):
        for table in ('aura_practice_account', 'aura_practice_events'):
            assert not pg.value("SELECT has_table_privilege('" + role + "','public." + table + "','SELECT');")
            denied = pg.sql('SELECT * FROM public.' + table + ';', role, check=False)
            assert denied.returncode and 'permission denied' in denied.stderr
        for call in ("aura_practice_load('{}'::jsonb)",
                     "aura_practice_commit(1,'{}'::jsonb,'[]'::jsonb,'x')",
                     'aura_practice_history(NULL,NULL,10,NULL)'):
            denied = pg.sql('SELECT public.' + call + ';', role, check=False)
            assert denied.returncode and 'permission denied' in denied.stderr
    passed('anon_authenticated_denied', 'Actual SELECT and all 3 RPC executions denied for both roles despite broad defaults')
    for role in ('anon', 'authenticated', 'service_role'):
        assert not pg.value("SELECT has_sequence_privilege('" + role + "','public.aura_practice_events_seq_seq','USAGE');"), role + ': inherited sequence grant remains'
        denied = pg.sql("SELECT nextval('public.aura_practice_events_seq_seq');", role, check=False)
        assert denied.returncode and 'permission denied' in denied.stderr
    for table in ('aura_practice_account', 'aura_practice_events'):
        assert not pg.value("SELECT has_table_privilege('service_role','public." + table + "','UPDATE');"), 'service_role can bypass RPC transaction validation'
        denied = pg.sql('UPDATE public.' + table + ' SET payload=payload;', 'service_role', check=False)
        assert denied.returncode and 'permission denied' in denied.stderr
    passed('rpc_only_privileges', 'Explicit sequence/table revocations override broad Supabase-like default grants; service role executes only the intended RPCs')
    # Prove RLS itself, independently of permission revocation. Undo test grants.
    for role in ('anon', 'authenticated'):
        pg.sql('GRANT SELECT,INSERT,UPDATE ON public.aura_practice_account TO ' + role + ';')
        assert pg.value('SELECT count(*) FROM public.aura_practice_account;', role) == 0
        assert pg.value('WITH changed AS (UPDATE public.aura_practice_account SET revision=999 RETURNING *) SELECT count(*) FROM changed;', role) == 0
        denied = pg.sql("INSERT INTO public.aura_practice_account(id,revision,payload,sha256) VALUES(1,1,'{}','bad');", role, check=False)
        assert denied.returncode and 'row-level security' in denied.stderr
        pg.sql('REVOKE ALL ON public.aura_practice_account FROM ' + role + ';')
    passed('rls_independent_of_grants', 'With temporary test grants, both roles see 0 rows, update 0 rows and INSERT violates RLS; grants revoked')

    for side in ('LONG', 'SHORT'):
        for exit_kind in ('MANUAL', 'TP', 'SL'):
            pg.reset_practice()
            quotes = OfflineQuotes()
            svc = Service(PostgreSQLStore(pg), quotes)
            command = body(side)
            opened = await svc.command('OPEN', command)
            assert opened['confirmed'] and not opened['duplicate']
            position = opened['view']['state']['position']
            if side == 'LONG' and exit_kind == 'MANUAL':
                saved = (await svc.view())['state']
                saved_events = await svc.store.history()
                pg.sql(migration)
                assert (await svc.view())['state'] == saved
                assert await svc.store.history() == saved_events
                passed('migration_preserves_open_account', 'Reapplying SQL with a persisted open position leaves account and journal identical')
                pg.restart()
                svc = Service(PostgreSQLStore(pg), quotes)
                assert (await svc.view())['state'] == saved
                passed('restart_open_position', 'Actual PostgreSQL container restart; new Service read identical persisted open state')
            duplicate = await svc.command('OPEN', command)
            assert duplicate['duplicate']
            quotes.set('101' if side == 'LONG' else '99')
            await svc.tick()
            # Repeating the identical observed quote must not append an UPDATE.
            revision = (await svc.view())['storage']['revision']
            await svc.tick()
            assert (await svc.view())['storage']['revision'] == revision
            if exit_kind == 'MANUAL':
                close = dict(request_id=str(uuid.uuid4()), position_id=position['id'])
                closed = await svc.command('CLOSE', close)
                assert closed['confirmed']
                assert (await svc.command('CLOSE', close))['duplicate']
            else:
                quotes.set(('105' if side == 'LONG' else '95') if exit_kind == 'TP' else ('97' if side == 'LONG' else '103'))
                await svc.tick()
            view = await svc.view()
            state = view['state']
            assert state['position'] is None
            events = list(reversed(view['events']))
            assert [e['kind'] for e in events] == ['OPEN', 'UPDATE', 'CLOSE']
            record = events[-1]['payload']
            with localcontext() as context:
                context.prec = 64
                q = D(position['size'])
                entry = D('100') * (D('1.0005') if side == 'LONG' else D('.9995'))
                raw = D(quotes.value['price'])
                exit_price = raw * (D('.9995') if side == 'LONG' else D('1.0005'))
                def fee(px):
                    return (px * q * D('.001')).quantize(D('.00000001'), rounding=ROUND_CEILING)
                gross = ((exit_price - entry) * q * (1 if side == 'LONG' else -1)).quantize(D('.00000001'), rounding=ROUND_HALF_EVEN)
                net = gross - fee(entry) - fee(exit_price)
                assert D(record['realized_pnl']) == net
                assert D(state['balance']) == D('10000') + net
                assert D(state['fees']) == fee(entry) + fee(exit_price)
                assert D(state['slippage']) == ((abs(entry-D('100'))+abs(exit_price-raw))*q).quantize(D('.00000001'), rounding=ROUND_HALF_EVEN)
            assert D(position['risk_usdt']) <= 50 and D(position['notional']) <= 2000
            trades.append(dict(scenario=side+'_'+exit_kind,initial_balance='10000',direction=side,
                entry=position['entry_price'],size=position['size'],sl=position['stop_loss'],tp=position['take_profit'],
                raw_exit=str(raw),exit=record['exit_price'],entry_fee=position['entry_fee'],exit_fee=record['exit_fee'],
                fees=state['fees'],slippage=state['slippage'],net_pnl=record['realized_pnl'],
                final_balance=state['balance'],open_count=1,update_count=1,close_count=1))
            if side == 'LONG' and exit_kind == 'MANUAL':
                pg.restart()
                assert (await Service(PostgreSQLStore(pg), quotes).view())['state'] == state
                passed('restart_closed_position', 'Actual PostgreSQL restart preserved final balance/fees/closed state')
            passed(side+'_'+exit_kind, 'Real PostgreSQL OPEN/UPDATE/CLOSE; original engine; independent Decimal fees/PnL/slippage; durable duplicate receipt')

    for operation in ('UPDATE public.aura_practice_events SET kind=kind;', 'DELETE FROM public.aura_practice_events;'):
        denied = pg.sql(operation, check=False)
        assert denied.returncode and 'APPEND_ONLY' in denied.stderr
    passed('append_only_events', 'Actual trigger rejects UPDATE and DELETE, including owner attempts')
    for role in ('anon', 'authenticated'):
        pg.sql('GRANT SELECT ON public.aura_practice_events TO ' + role + ';')
        assert pg.value('SELECT count(*) FROM public.aura_practice_events;', role) == 0
        pg.sql('REVOKE ALL ON public.aura_practice_events FROM ' + role + ';')
    passed('journal_rls_with_rows', 'Both browser roles see zero persisted events even with a temporary SELECT grant; grants revoked')

    pg.reset_practice()
    env = await store.load(int(time.time()))
    quote = OfflineQuotes().value
    args = commit_args(env, quote, body())
    malformed = deepcopy(args)
    second = deepcopy(malformed['new_events'][0])
    second.update(id='practice:invalid-second', sha256='0'*64)
    malformed['new_events'].append(second)
    assert pg.rpc('aura_practice_commit', dict(args, new_events=[]))['error'] == 'WRITE_LIMIT'
    try:
        await asyncio.to_thread(pg.rpc, 'aura_practice_commit', malformed)
    except subprocess.CalledProcessError as exc:
        assert 'INVALID_EVENT' in exc.stderr
    else:
        raise AssertionError('Invalid second event was accepted')
    assert (await store.load(int(time.time())))['revision'] == env['revision']
    assert await store.history() == []
    passed('atomic_invalid_second_event', 'First INSERT rolled back when second event failed; account revision/state unchanged')
    pg.sql("CREATE FUNCTION public.offline_fail_account_update() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'OFFLINE_DB_FAILURE'; END $$; "
           "CREATE TRIGGER offline_fail BEFORE UPDATE ON public.aura_practice_account FOR EACH ROW EXECUTE FUNCTION public.offline_fail_account_update();")
    svc = Service(PostgreSQLStore(pg), OfflineQuotes())
    recover_command = body()
    try:
        await svc.command('OPEN', recover_command)
    except subprocess.CalledProcessError as exc:
        assert 'OFFLINE_DB_FAILURE' in exc.stderr
    else:
        raise AssertionError('Injected DB failure returned a confirmed OPEN')
    assert await store.history() == []
    unchanged = await store.load(int(time.time()))
    assert unchanged['state']['position'] is None and unchanged['state']['fees'] == '0'
    pg.sql('DROP TRIGGER offline_fail ON public.aura_practice_account; DROP FUNCTION public.offline_fail_account_update();')
    assert (await svc.command('OPEN', recover_command))['confirmed']
    passed('atomic_database_failure_and_recovery', 'Real account UPDATE failure rolled back inserted OPEN and fees; same UUID succeeded after trigger removal')

    pg.reset_practice()
    env = await store.load(int(time.time()))
    first, second = (commit_args(env, OfflineQuotes().value, body()) for _ in range(2))
    barrier = threading.Barrier(2)
    def compete(arguments):
        barrier.wait(timeout=10)
        return pg.rpc('aura_practice_commit', arguments)
    with ThreadPoolExecutor(max_workers=2) as pool:
        f1, f2 = pool.submit(compete, first), pool.submit(compete, second)
        results = [f1.result(), f2.result()]
    assert sum(x.get('error') == 'CONCURRENT_UPDATE' for x in results) == 1
    assert len(await store.history()) == 1
    winning = first if not results[0].get('error') else second
    assert pg.rpc('aura_practice_commit', winning)['duplicate'] is True
    conflict = deepcopy(winning)
    conflict['new_events'][0]['command_hash'] = 'different-offline-command'
    assert pg.rpc('aura_practice_commit', conflict)['error'] == 'IDEMPOTENCY_CONFLICT'
    passed('concurrent_open_and_bound_duplicate', 'Two independent psql connections, same revision: one OPEN, one CONCURRENT_UPDATE; duplicate UUID no second fee; changed hash rejected')
    env = await store.load(int(time.time()))
    close_quote = dict(env['state']['last_quote'], time_ms=int(time.time()*1000),
                       trade_id=env['state']['last_quote']['trade_id']+1)
    close_args = [commit_args(env, close_quote,
                  dict(request_id=str(uuid.uuid4()), position_id=env['state']['position']['id']), 'CLOSE') for _ in range(2)]
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        f1, f2 = [pool.submit(compete, a) for a in close_args]
        results = [f1.result(), f2.result()]
    assert sum(x.get('error') == 'CONCURRENT_UPDATE' for x in results) == 1
    winner = close_args[0] if not results[0].get('error') else close_args[1]
    assert pg.rpc('aura_practice_commit', winner)['duplicate'] is True
    assert sorted(e['kind'] for e in await store.history()) == ['CLOSE','OPEN']
    assert (await store.load(int(time.time())))['state']['trades'] == 1
    passed('concurrent_close', 'Two independent close transactions: one CLOSE, one CONCURRENT_UPDATE; duplicate CLOSE does not charge a second fee')

    pg.reset_practice()
    env = await store.load(int(time.time()))
    stale = commit_args(env, OfflineQuotes().value, body())
    state = json.loads(stale['new_state']['payload'])
    state['last_quote']['time_ms'] = int(time.time()*1000) - 20000
    stale['new_state'] = packed(state)
    assert pg.rpc('aura_practice_commit', stale)['error'] == 'STALE_QUOTE_AT_COMMIT'
    assert await store.history() == []
    passed('database_clock_quote_freshness', '20-second-old quote rejected at SQL commit; no OPEN persisted')
    assert pg.auto42_snapshot() == before
    passed('auto42_unchanged_entire_run', 'Auto42 table/data/DDL/ACL/sequence/trigger dump and function definitions unchanged through all Practice tests and PostgreSQL restarts')
    return dict(checks=checks,trades=trades,auto42_before_sha256=before,auto42_after_sha256=pg.auto42_snapshot())


def run(output):
    if os.getenv('RENDER'):
        raise ValueError('Local verification only; Render forbidden')
    if output.exists():
        raise ValueError('Use a new output path')
    container = 'aura-practice-pg-' + uuid.uuid4().hex[:12]
    docker('info', '--format', '{{.ServerVersion}}')
    # Never start/reconfigure the daemon or use a remote Docker context.
    docker('run', '-d', '--name', container, '--label', 'aura.practice.verification=true',
           '--network', 'none', '--memory', '512m', '--cpus', '1',
           '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_DB='+DATABASE, IMAGE, timeout=180)
    try:
        pg = PG(container)
        for _ in range(100):
            # The image's temporary init server accepts Unix sockets before
            # shutdown; TCP readiness proves the final post-init server is up.
            if docker('exec', container, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres', '-d', DATABASE, check=False).returncode == 0:
                break
            time.sleep(.1)
        else:
            raise RuntimeError('PostgreSQL startup failed')
        result = asyncio.run(verify(pg))
        result.update(POSTGRESQL_VERIFIED=True,RLS_VERIFIED=True,OPEN_CLOSE_VERIFIED=True,
            PRODUCTION_READY=False,RENDER_STAGING_VERIFIED=False,REAL_SUPABASE_CYCLE_VERIFIED=False,
            scope='REAL_LOCAL_POSTGRESQL_OFFLINE_QUOTES_SQL_RPC_ADAPTER_NOT_POSTGREST_OR_RENDER',
            checked_at=datetime.now(timezone.utc).isoformat(),
            postgres_version=pg.sql('SELECT version();'),docker_image=IMAGE,
            migration_sha256=hashlib.sha256((ROOT/'scripts/practice_schema.sql').read_bytes()).hexdigest(),
            production_supabase_access=False,production_writes=False,real_orders=False,
            limits=dict(memory='512 MiB',cpus=1,network='none',published_ports=0),
            adapter_limitation='Existing Service, Store envelope/commit/history validation and engine; SQL RPC adapter over psql. No mocked database. HTTP/PostgREST/auth gateway not exercised.')
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('x') as stream:
            json.dump(result,stream,indent=2);stream.write('\n')
        print(json.dumps(dict(output=str(output),checks=len(result['checks']),trades=len(result['trades']),
                              POSTGRESQL_VERIFIED=True,RLS_VERIFIED=True,OPEN_CLOSE_VERIFIED=True,PRODUCTION_READY=False)))
        return result
    finally:
        docker('rm', '-fv', container, check=False)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)

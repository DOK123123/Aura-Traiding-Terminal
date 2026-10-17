-- PAPER PRACTICE ONLY. Execute manually after owner review in Supabase SQL editor.
-- New aura_practice_* objects only; no access to existing Auto42/Paper/Forward tables.
BEGIN;
create extension if not exists pgcrypto with schema extensions;
create table if not exists public.aura_practice_account (
 id integer primary key check (id=1), revision bigint not null,
 payload text not null, sha256 text not null,
 saved_at timestamptz
);
-- Additive migration: historical save time remains UNKNOWN, never fabricated.
alter table public.aura_practice_account add column if not exists saved_at timestamptz;
create table if not exists public.aura_practice_events (
 seq bigint generated always as identity primary key,id text unique not null,
 epoch text not null,kind text not null,created_at bigint not null,
 ingested_at timestamptz not null default clock_timestamp(),payload text not null,sha256 text not null
);
create index if not exists aura_practice_epoch on public.aura_practice_events(epoch,seq);
alter table public.aura_practice_account enable row level security;
alter table public.aura_practice_events enable row level security;
-- Supabase default privileges may grant new tables/sequences to all API roles.
-- Even service_role uses SECURITY DEFINER RPCs, never direct ledger writes.
revoke all on public.aura_practice_account,public.aura_practice_events from public,anon,authenticated,service_role;
revoke all on sequence public.aura_practice_events_seq_seq from public,anon,authenticated,service_role;
create or replace function public.aura_practice_immutable() returns trigger language plpgsql as $$
begin raise exception 'APPEND_ONLY'; end $$;
drop trigger if exists aura_practice_no_change on public.aura_practice_events;
create trigger aura_practice_no_change before update or delete on public.aura_practice_events
 for each row execute function public.aura_practice_immutable();

create or replace function public.aura_practice_load(seed jsonb) returns jsonb
language plpgsql security definer set search_path=public,extensions,pg_temp set statement_timeout='8s' set lock_timeout='3s' as $$
declare r public.aura_practice_account; s jsonb;
begin
 s := (seed->>'payload')::jsonb;
 if seed->>'sha256' <> encode(extensions.digest(convert_to(seed->>'payload','UTF8'),'sha256'),'hex')
    or s->>'mode' is distinct from 'ON' or s->>'practice_scope' is distinct from 'PAPER_PRACTICE_V1' or left(s->>'epoch',9) is distinct from 'PRACTICE_' or s->>'balance' is distinct from '10000' or s->>'equity' is distinct from '10000'
    or s->>'version' is distinct from 'AURA_AUTO_PAPER_4.2.0' or s->'position' is distinct from 'null'::jsonb then
   return jsonb_build_object('error','CORRUPT_PORTFOLIO'); end if;
 insert into public.aura_practice_account(id,revision,payload,sha256,saved_at) values(1,1,seed->>'payload',seed->>'sha256',clock_timestamp()) on conflict do nothing;
 select * into r from public.aura_practice_account where id=1;
 return jsonb_build_object('revision',r.revision,'payload',r.payload,'sha256',r.sha256,'last_saved_at',floor(extract(epoch from r.saved_at))::bigint);
end $$;

create or replace function public.aura_practice_commit(expected_revision bigint,new_state jsonb,new_events jsonb,operation_key text) returns jsonb
language plpgsql security definer set search_path=public,extensions,pg_temp set statement_timeout='8s' set lock_timeout='3s' as $$
declare r public.aura_practice_account; e jsonb; p jsonb; s jsonb;
begin
 select * into r from public.aura_practice_account where id=1 for update;
 if not found then return jsonb_build_object('error','CORRUPT_PORTFOLIO'); end if;
 if exists(select 1 from public.aura_practice_events where id=operation_key) then
   if (select payload::jsonb->>'command_hash' from public.aura_practice_events where id=operation_key) is distinct from (new_events->0->>'command_hash') then
    return jsonb_build_object('error','IDEMPOTENCY_CONFLICT'); end if;
   return jsonb_build_object('revision',r.revision,'payload',r.payload,'sha256',r.sha256,'last_saved_at',floor(extract(epoch from r.saved_at))::bigint,'duplicate',true); end if;
 if r.revision<>expected_revision then return jsonb_build_object('error','CONCURRENT_UPDATE'); end if;
 if jsonb_typeof(new_events)<>'array' or jsonb_array_length(new_events) not between 1 and 100
    or octet_length(new_state->>'payload')>65536 then return jsonb_build_object('error','WRITE_LIMIT'); end if;
 s := (new_state->>'payload')::jsonb;
 if new_state->>'sha256' <> encode(extensions.digest(convert_to(new_state->>'payload','UTF8'),'sha256'),'hex')
    or s->>'version' is distinct from 'AURA_AUTO_PAPER_4.2.0' or s->>'mode' is distinct from 'ON' or s->>'practice_scope' is distinct from 'PAPER_PRACTICE_V1' or left(s->>'epoch',9) is distinct from 'PRACTICE_' then
    return jsonb_build_object('error','CORRUPT_PORTFOLIO'); end if;
 -- Evaluate quote age on the database clock, including row-lock/network delay.
 if (s->'last_quote'->>'time_ms') is null or
    floor(extract(epoch from clock_timestamp())*1000)-(s->'last_quote'->>'time_ms')::bigint not between -2000 and 10000 then
   return jsonb_build_object('error','STALE_QUOTE_AT_COMMIT'); end if;
 if not exists(select 1 from jsonb_array_elements(new_events) x where x->>'id'=operation_key) then
   return jsonb_build_object('error','INVALID_EVENT'); end if;
 for e in select * from jsonb_array_elements(new_events) loop
   p := (e->>'payload')::jsonb;
   if octet_length(e->>'payload')>65536 or length(e->>'id')>200 or e->>'epoch'<>s->>'epoch'
      or p->'payload'->>'practice_scope' is distinct from 'PAPER_PRACTICE_V1' or p->'payload'->>'execution_mode' is distinct from 'PAPER_ONLY' or p->'payload'->>'real_money_execution' is distinct from 'DISABLED'
      or e->>'sha256' <> encode(extensions.digest(convert_to(e->>'payload','UTF8'),'sha256'),'hex') then
      raise exception 'INVALID_EVENT'; end if;
   insert into public.aura_practice_events(id,epoch,kind,created_at,payload,sha256)
     values(e->>'id',e->>'epoch',e->>'kind',(e->>'created_at')::bigint,e->>'payload',e->>'sha256');
 end loop;
 update public.aura_practice_account set revision=revision+1,payload=new_state->>'payload',sha256=new_state->>'sha256',saved_at=clock_timestamp() where id=1 returning * into r;
 return jsonb_build_object('revision',r.revision,'payload',r.payload,'sha256',r.sha256,'last_saved_at',floor(extract(epoch from r.saved_at))::bigint,'duplicate',false);
end $$;

create or replace function public.aura_practice_history(selected_epoch text default null,after_seq bigint default null,row_limit integer default 50,event_id text default null) returns jsonb
language plpgsql security definer set search_path=public,extensions,pg_temp set statement_timeout='8s' set lock_timeout='3s' as $$
declare result jsonb;
begin
 if row_limit not between 1 and 200 then return jsonb_build_object('error','WRITE_LIMIT'); end if;
 if event_id is not null then
  select coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) into result from
    (select seq,payload,sha256 from public.aura_practice_events where id=event_id limit 1) t;
 elsif after_seq is not null then
  select coalesce(jsonb_agg(to_jsonb(t) order by seq),'[]'::jsonb) into result from
    (select seq,payload,sha256 from public.aura_practice_events where seq>after_seq order by seq limit row_limit) t;
 else
  select coalesce(jsonb_agg(to_jsonb(t) order by seq desc),'[]'::jsonb) into result from
    (select seq,payload,sha256 from public.aura_practice_events where selected_epoch is null or epoch=selected_epoch order by seq desc limit row_limit) t;
 end if;return result;
end $$;
revoke all on function public.aura_practice_immutable() from public,anon,authenticated;
revoke all on function public.aura_practice_load(jsonb) from public,anon,authenticated;
revoke all on function public.aura_practice_commit(bigint,jsonb,jsonb,text) from public,anon,authenticated;
revoke all on function public.aura_practice_history(text,bigint,integer,text) from public,anon,authenticated;
grant execute on function public.aura_practice_load(jsonb),public.aura_practice_commit(bigint,jsonb,jsonb,text),public.aura_practice_history(text,bigint,integer,text) to service_role;

NOTIFY pgrst, 'reload schema';
COMMIT;

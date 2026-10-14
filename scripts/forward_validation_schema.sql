-- Run explicitly in a dedicated Supabase project's SQL editor. No trading tables.
create extension if not exists pgcrypto with schema extensions;
create table if not exists public.aura_forward_records (
 seq bigint generated always as identity primary key,
 id text not null unique check(length(id)<=160),kind text not null check(kind in ('PRED','OUTCOME','CORRECTION','TICK','COMPLETE','FAILURE')),
 created_ms bigint not null,ingested_ms bigint not null default (floor(extract(epoch from clock_timestamp())*1000)::bigint),
 cohort text not null,tf text not null,closed_at bigint not null,ref text not null,horizon integer not null,
 payload text not null check(octet_length(payload)<=65536),sha256 text not null check(length(sha256)=64));
create unique index if not exists aura_forward_pred_unique on public.aura_forward_records(cohort,tf,closed_at) where kind='PRED';
create unique index if not exists aura_forward_outcome_unique on public.aura_forward_records(ref,horizon) where kind='OUTCOME';
create index if not exists aura_forward_ref_idx on public.aura_forward_records(ref);
create index if not exists aura_forward_kind_idx on public.aura_forward_records(kind,cohort,seq);
alter table public.aura_forward_records enable row level security;
revoke all on public.aura_forward_records from anon,authenticated;
create or replace function public.aura_forward_immutable() returns trigger language plpgsql as $$
begin raise exception 'APPEND_ONLY'; end $$;
drop trigger if exists aura_forward_no_changes on public.aura_forward_records;
create trigger aura_forward_no_changes before update or delete on public.aura_forward_records for each row execute function public.aura_forward_immutable();

create or replace function public.aura_forward_append(p_records jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog,public,extensions as $$
declare r jsonb;b jsonb;old public.aura_forward_records%rowtype;p public.aura_forward_records%rowtype;
 inserted integer:=0;duplicates integer:=0;corrections integer:=0;affected integer;
 now_ms bigint:=floor(extract(epoch from clock_timestamp())*1000)::bigint;step integer;refid text;corr text;corrid text;
begin
 if jsonb_typeof(p_records)<>'array' or jsonb_array_length(p_records)>100 then raise exception 'WRITE_LIMIT';end if;
 for r in select value from jsonb_array_elements(p_records) order by value->>'id' loop
  perform pg_advisory_xact_lock(hashtextextended(r->>'id',0));
  if r->>'kind' not in ('PRED','OUTCOME','CORRECTION','TICK','COMPLETE','FAILURE') or length(r->>'id')>160 or octet_length(r->>'payload')>65536 or
     encode(extensions.digest(convert_to(r->>'payload','UTF8'),'sha256'),'hex')<>r->>'sha256' then raise exception 'INVALID_RECORD';end if;
  b:=(r->>'payload')::jsonb;
  select * into old from public.aura_forward_records where id=r->>'id' for update;
  if found then
   duplicates:=duplicates+1;
   if r->>'kind' in ('PRED','OUTCOME') and (old.payload::jsonb)->>'fingerprint' is distinct from b->>'fingerprint' then
    refid:=case when r->>'kind'='PRED' then r->>'id' else r->>'ref' end;
    corrid:='correction:'||encode(extensions.digest(convert_to((r->>'id')||':'||(b->>'fingerprint'),'UTF8'),'sha256'),'hex');
    corr:=jsonb_build_object('prediction_id',refid,'reference_id',r->>'id','old_sha256',old.sha256,
           'proposed_record',b,'reason','IMMUTABLE_SOURCE_CORRECTION','fingerprint',b->>'fingerprint')::text;
    insert into public.aura_forward_records(id,kind,created_ms,cohort,tf,closed_at,ref,horizon,payload,sha256)
     values(corrid,'CORRECTION',now_ms,r->>'cohort',r->>'tf',(r->>'closed_at')::bigint,refid,0,corr,encode(extensions.digest(convert_to(corr,'UTF8'),'sha256'),'hex')) on conflict do nothing;
    get diagnostics affected=row_count;corrections:=corrections+affected;
   end if;
   continue;
  end if;
  if r->>'kind'='PRED' then
   step:=case r->>'tf' when '15m' then 900 when '1h' then 3600 when '4h' then 14400 else 0 end;
   if step=0 or b->>'exchange'<>'Binance' or b->>'market_type'<>'SPOT' or b->>'symbol'<>'BTCUSDT' or b->>'id'<>r->>'id' or
      (b->>'closed_at')::bigint<>(r->>'closed_at')::bigint or (r->>'closed_at')::bigint%step<>0 or
      (r->>'created_ms')::bigint<(r->>'closed_at')::bigint*1000 or
      (r->>'created_ms')::bigint>=((r->>'closed_at')::bigint+step)*1000 or
      now_ms<(r->>'closed_at')::bigint*1000 or now_ms>=((r->>'closed_at')::bigint+step)*1000 or abs((r->>'created_ms')::bigint-now_ms)>120000 then
        raise exception 'RETROACTIVE_OR_INVALID_PREDICTION';end if;
  elsif r->>'kind'='OUTCOME' then
   select * into p from public.aura_forward_records where id=r->>'ref' and kind='PRED';
   step:=case p.tf when '15m' then 900 when '1h' then 3600 when '4h' then 14400 else 0 end;
   if not found or (r->>'horizon')::integer not in (4,8,16,32) or b->>'prediction_id'<>p.id or
      (b->>'target_closed_at')::bigint<>p.closed_at+(r->>'horizon')::integer*step or
      now_ms<(b->>'target_closed_at')::bigint*1000 then raise exception 'PREMATURE_OUTCOME';end if;
  end if;
  insert into public.aura_forward_records(id,kind,created_ms,cohort,tf,closed_at,ref,horizon,payload,sha256)
   values(r->>'id',r->>'kind',(r->>'created_ms')::bigint,r->>'cohort',r->>'tf',(r->>'closed_at')::bigint,r->>'ref',(r->>'horizon')::integer,r->>'payload',r->>'sha256') on conflict do nothing;
  get diagnostics affected=row_count;inserted:=inserted+affected;
 end loop;
 return jsonb_build_object('inserted',inserted,'duplicates',duplicates,'corrections',corrections);
end $$;

create or replace function public.aura_forward_read(p_mode text,p_after bigint default 0,p_limit integer default 100,p_through bigint default null,p_cohort text default null)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare result jsonb;
begin
 if p_limit<1 or p_limit>200 then raise exception 'READ_LIMIT';end if;
 if p_mode='recent' then
  with picked as (select id from public.aura_forward_records where kind='PRED' and (p_cohort is null or cohort=p_cohort) order by seq desc limit p_limit)
  select coalesce(jsonb_agg(to_jsonb(r) order by seq),'[]'::jsonb) into result from public.aura_forward_records r where r.id in(select id from picked) or r.ref in(select id from picked);
 elsif p_mode='pending' then
  select coalesce(jsonb_agg(to_jsonb(r) order by seq),'[]'::jsonb) into result from (
   select p.* from public.aura_forward_records p where p.kind='PRED' and exists(
    select 1 from (values(4),(8),(16),(32)) hs(h) where p.closed_at+hs.h*(case p.tf when '15m' then 900 when '1h' then 3600 else 14400 end)<=extract(epoch from clock_timestamp())
    and not exists(select 1 from public.aura_forward_records o where o.kind='OUTCOME' and o.ref=p.id and o.horizon=hs.h)) order by p.seq limit p_limit) r;
 elsif p_mode='run' then
  select coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) into result from public.aura_forward_records r where id='tick:'||p_after::text||':complete';
 elsif p_mode='export' then
  select coalesce(jsonb_agg(to_jsonb(r) order by seq),'[]'::jsonb) into result from (select * from public.aura_forward_records
    where seq>p_after and (p_through is null or seq<=p_through) order by seq limit p_limit) r;
 else raise exception 'READ_MODE';end if;
 if jsonb_array_length(result)>2000 then raise exception 'READ_LIMIT';end if;
 return result;
end $$;

create or replace function public.aura_forward_status(p_cohort text default null) returns jsonb
language sql security definer set search_path=pg_catalog,public as $$
 with counts as(select kind,count(*) n,max(created_ms) last_ms from public.aura_forward_records group by kind),
 preds as(select tf,closed_at,lag(closed_at) over(partition by tf order by closed_at) prev from public.aura_forward_records where kind='PRED' and (p_cohort is null or cohort=p_cohort)),
 tails as(select tf,max(closed_at) at from preds group by tf),
 ticks as(select created_ms/300000 slot,lag(created_ms/300000) over(order by created_ms) prev from public.aura_forward_records where kind='TICK'),
 cohorts as(select cohort,count(*) predictions,max(seq) last_seq from public.aura_forward_records where kind='PRED' group by cohort order by max(seq) desc limit 100)
 select jsonb_build_object(
 'evaluated_predictions',(select count(distinct ref) from public.aura_forward_records where kind='OUTCOME' and payload::jsonb->>'quality'='COMPLETE'),
 'invalid_outcomes',(select count(*) from public.aura_forward_records where kind='OUTCOME' and payload::jsonb->>'quality'<>'COMPLETE'),
 'last_successful_evaluation_ms',(select max(created_ms) from public.aura_forward_records where kind='OUTCOME' and payload::jsonb->>'quality'='COMPLETE'),
 'counts',coalesce((select jsonb_object_agg(kind,n) from counts),'{}'::jsonb),
 'last',coalesce((select jsonb_object_agg(kind,last_ms) from counts),'{}'::jsonb),
 'total_rows',(select count(*) from public.aura_forward_records),'max_seq',(select coalesce(max(seq),0) from public.aura_forward_records),
 'missed_closed_candles',coalesce((select sum(greatest(0,(closed_at-prev)/(case tf when '15m' then 900 when '1h' then 3600 else 14400 end)-1)) from preds),0)+
 coalesce((select sum(greatest(0,(floor(extract(epoch from clock_timestamp())/(case tf when '15m' then 900 when '1h' then 3600 else 14400 end))*(case tf when '15m' then 900 when '1h' then 3600 else 14400 end)-at)/(case tf when '15m' then 900 when '1h' then 3600 else 14400 end))) from tails),0),
 'missed_runs',coalesce((select sum(greatest(0,slot-prev-1)) from ticks),0)+coalesce((select greatest(0,floor(extract(epoch from clock_timestamp())/300)-max(slot)) from ticks),0),
 'monitoring_scope','Since first recorded capture/tick only','cohorts',coalesce((select jsonb_agg(to_jsonb(c)-'last_seq') from cohorts c),'[]'::jsonb));
$$;
revoke all on function public.aura_forward_append(jsonb) from public,anon,authenticated;
revoke all on function public.aura_forward_read(text,bigint,integer,bigint,text) from public,anon,authenticated;
revoke all on function public.aura_forward_status(text) from public,anon,authenticated;
grant execute on function public.aura_forward_append(jsonb) to service_role;
grant execute on function public.aura_forward_read(text,bigint,integer,bigint,text) to service_role;
grant execute on function public.aura_forward_status(text) to service_role;

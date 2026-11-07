-- Isolated Preview only. Private schema preserves the existing wallet scope guard.
BEGIN;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM public.aura_manual_preview_scope WHERE id=1
 AND project_ref='kkxdftdojvnsjqlrulpb' AND scope='AURA_MANUAL_PREVIEW_ONLY_V1') THEN
 RAISE EXCEPTION 'PREVIEW_SCOPE_REQUIRED'; END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS aura5_signals;
REVOKE ALL ON SCHEMA aura5_signals FROM PUBLIC,anon,authenticated;
GRANT USAGE ON SCHEMA aura5_signals TO service_role;
CREATE TABLE IF NOT EXISTS aura5_signals.meta(id integer PRIMARY KEY CHECK(id=1), version bigint NOT NULL DEFAULT 0);
INSERT INTO aura5_signals.meta VALUES(1,0) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS aura5_signals.records(id text PRIMARY KEY, body jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS aura5_signals.events(id text PRIMARY KEY, body jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS aura5_signals.subscriptions(id text PRIMARY KEY, body jsonb NOT NULL,
 enabled boolean NOT NULL DEFAULT true, candidate boolean NOT NULL DEFAULT false, updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS aura5_signals.outbox(id text PRIMARY KEY, subscription_id text NOT NULL REFERENCES aura5_signals.subscriptions(id),
 scenario_id text, kind text NOT NULL, state text NOT NULL DEFAULT 'PENDING', created_at timestamptz NOT NULL DEFAULT now(),
 attempted_at timestamptz, finished_at timestamptz, code integer);
CREATE INDEX IF NOT EXISTS aura5_outbox_pending ON aura5_signals.outbox(created_at) WHERE state='PENDING';
ALTER TABLE aura5_signals.meta ENABLE ROW LEVEL SECURITY;
ALTER TABLE aura5_signals.records ENABLE ROW LEVEL SECURITY;
ALTER TABLE aura5_signals.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE aura5_signals.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE aura5_signals.outbox ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA aura5_signals FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA aura5_signals TO service_role;
CREATE OR REPLACE FUNCTION public.aura5_signals_rpc(p_action text,p_data jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v bigint; r jsonb; e jsonb; sid text; job record; epoch double precision := extract(epoch from clock_timestamp());
BEGIN
 IF current_user <> 'service_role' OR (public.aura_manual_preview_guard()->>'isolated')::boolean IS DISTINCT FROM true THEN
 RAISE EXCEPTION 'PREVIEW_SCOPE_REQUIRED'; END IF;
 IF octet_length(p_data::text)>2000000 THEN RAISE EXCEPTION 'PAYLOAD_LIMIT'; END IF;
 SELECT version INTO v FROM aura5_signals.meta WHERE id=1 FOR UPDATE;
 IF p_action='load' THEN
 RETURN jsonb_build_object('version',v,'records',coalesce((SELECT jsonb_agg(x.body ORDER BY x.id) FROM (SELECT id,body FROM aura5_signals.records WHERE id>coalesce(p_data->>'after','') ORDER BY id LIMIT 50) x),'[]'::jsonb));
 ELSIF p_action='commit' THEN
 IF v<>(p_data->>'version')::bigint THEN RETURN jsonb_build_object('conflict',true); END IF;
 IF jsonb_array_length(p_data->'records')>100 OR jsonb_array_length(p_data->'events')>100 THEN RAISE EXCEPTION 'BATCH_LIMIT'; END IF;
 FOR r IN SELECT value FROM jsonb_array_elements(p_data->'records') LOOP
 IF r->>'id' !~ '^[a-f0-9]{64}$' OR r->>'status' NOT IN ('CANDIDATE','WATCH','INVALIDATED','EXPIRED','UNKNOWN') THEN RAISE EXCEPTION 'INVALID_RECORD'; END IF;
 IF r->>'status' IN ('CANDIDATE','WATCH') AND ((r->>'refreshed_at')::double precision < epoch-5 OR (r->>'valid_until')::double precision<=epoch) THEN RAISE EXCEPTION 'STALE_COMMIT'; END IF;
 -- The global version row is already locked. Completed episodes are immutable
 -- even if a stale/incorrect caller attempts to re-admit the same identity.
 IF EXISTS(SELECT 1 FROM aura5_signals.records old WHERE old.id=r->>'id'
           AND old.body->>'status' IN ('INVALIDATED','EXPIRED','UNKNOWN') AND old.body<>r)
 THEN RAISE EXCEPTION 'SIGNAL_TERMINAL_IMMUTABLE'; END IF;
 INSERT INTO aura5_signals.records VALUES(r->>'id',r) ON CONFLICT(id) DO UPDATE SET body=excluded.body;
 END LOOP;
 IF (SELECT count(*) FROM aura5_signals.records)>5000 THEN RAISE EXCEPTION 'RETENTION_LIMIT'; END IF;
 FOR e IN SELECT value FROM jsonb_array_elements(p_data->'events') LOOP
 INSERT INTO aura5_signals.events VALUES(e->>'id',e,now()) ON CONFLICT DO NOTHING;
 IF FOUND AND e->>'to' IN ('WATCH','CANDIDATE') THEN
 INSERT INTO aura5_signals.outbox(id,subscription_id,scenario_id,kind)
 SELECT (e->>'id')||':'||s.id,s.id,e->>'scenario_id',e->>'to' FROM aura5_signals.subscriptions s
 WHERE s.enabled AND (e->>'to'='WATCH' OR s.candidate) ON CONFLICT DO NOTHING;
 END IF;
 END LOOP;
 UPDATE aura5_signals.meta SET version=version+1 WHERE id=1 RETURNING version INTO v;
 RETURN jsonb_build_object('version',v);
 ELSIF p_action='subscribe' THEN
 sid:=p_data->>'id';
 IF sid !~ '^[a-f0-9]{64}$' OR octet_length((p_data->'subscription')::text)>4096 THEN RAISE EXCEPTION 'INVALID_SUBSCRIPTION'; END IF;
 IF (SELECT count(*) FROM aura5_signals.subscriptions)>=32 AND NOT EXISTS(SELECT 1 FROM aura5_signals.subscriptions WHERE id=sid) THEN RAISE EXCEPTION 'SUBSCRIPTION_LIMIT'; END IF;
 INSERT INTO aura5_signals.subscriptions(id,body,enabled,candidate) VALUES(sid,p_data->'subscription',true,(p_data->>'candidate')::boolean)
 ON CONFLICT(id) DO UPDATE SET body=excluded.body,enabled=true,candidate=excluded.candidate,updated_at=now();
 RETURN jsonb_build_object('id',sid,'state','SUBSCRIBED');
 ELSIF p_action='unsubscribe' THEN
 UPDATE aura5_signals.subscriptions SET enabled=false,body='{}'::jsonb,updated_at=now() WHERE id=p_data->>'id';
 RETURN jsonb_build_object('state','DISABLED');
 ELSIF p_action='test' THEN
 sid:=p_data->>'id';
 IF NOT EXISTS(SELECT 1 FROM aura5_signals.subscriptions WHERE id=sid AND enabled) THEN RAISE EXCEPTION 'NOT_SUBSCRIBED'; END IF;
 IF EXISTS(SELECT 1 FROM aura5_signals.outbox WHERE subscription_id=sid AND kind='TEST' AND created_at>now()-interval '1 minute') THEN RAISE EXCEPTION 'TEST_RATE_LIMIT'; END IF;
 INSERT INTO aura5_signals.outbox(id,subscription_id,kind) VALUES('test:'||sid||':'||floor(epoch/60)::text,sid,'TEST') ON CONFLICT DO NOTHING;
 RETURN jsonb_build_object('state','QUEUED_NOT_DELIVERED');
 ELSIF p_action='claim' THEN
 UPDATE aura5_signals.outbox SET state='UNKNOWN_SEND_OUTCOME',finished_at=now() WHERE state='SENDING' AND attempted_at<now()-interval '1 minute';
 UPDATE aura5_signals.outbox o SET state='SKIPPED_EXPIRED',finished_at=now() WHERE state='PENDING' AND (created_at<now()-interval '2 minutes'
 OR NOT EXISTS(SELECT 1 FROM aura5_signals.subscriptions s WHERE s.id=o.subscription_id AND s.enabled)
 OR (kind<>'TEST' AND NOT EXISTS(SELECT 1 FROM aura5_signals.records r WHERE r.id=o.scenario_id AND r.body->>'status'=o.kind AND (o.kind<>'CANDIDATE' OR (r.body->>'score')::integer>=70)
 AND (r.body->>'valid_until')::double precision>epoch AND (r.body->>'refreshed_at')::double precision>=epoch-5)));
 SELECT o.*,s.body AS subscription INTO job FROM aura5_signals.outbox o JOIN aura5_signals.subscriptions s ON s.id=o.subscription_id
 WHERE o.state='PENDING' ORDER BY o.created_at LIMIT 1 FOR UPDATE OF o SKIP LOCKED;
 IF NOT FOUND THEN RETURN null; END IF;
 UPDATE aura5_signals.outbox SET state='SENDING',attempted_at=now() WHERE id=job.id;
 RETURN jsonb_build_object('id',job.id,'subscription_id',job.subscription_id,'subscription',job.subscription,'scenario_id',job.scenario_id,'kind',job.kind);
 ELSIF p_action='finish' THEN
 IF p_data->>'state' NOT IN ('ACCEPTED_BY_PUSH_SERVICE','REJECTED_BY_PUSH_SERVICE','UNKNOWN_SEND_OUTCOME') THEN RAISE EXCEPTION 'INVALID_STATE'; END IF;
 UPDATE aura5_signals.outbox SET state=p_data->>'state',code=(p_data->>'code')::integer,finished_at=now() WHERE id=p_data->>'id' AND state='SENDING';
 IF (p_data->>'code')::integer IN (404,410) THEN
 UPDATE aura5_signals.subscriptions SET enabled=false,body='{}'::jsonb WHERE id=(SELECT subscription_id FROM aura5_signals.outbox WHERE id=p_data->>'id'); END IF;
 RETURN jsonb_build_object('state',p_data->>'state');
 ELSIF p_action='delivery' THEN
 RETURN coalesce((SELECT jsonb_agg(jsonb_build_object('kind',kind,'state',state,'code',code,'at',created_at)) FROM
 (SELECT kind,state,code,created_at FROM aura5_signals.outbox WHERE subscription_id=p_data->>'id' ORDER BY created_at DESC LIMIT 30) x),'[]'::jsonb);
 END IF;
 RAISE EXCEPTION 'INVALID_ACTION';
END $$;
REVOKE ALL ON FUNCTION public.aura5_signals_rpc(text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.aura5_signals_rpc(text,jsonb) TO service_role;
COMMIT;

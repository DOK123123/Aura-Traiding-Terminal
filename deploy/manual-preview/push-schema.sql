-- Dedicated existing Preview only. Contains no key material or subscribers.
BEGIN;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM public.aura_manual_preview_scope WHERE id=1
  AND scope='AURA_MANUAL_PREVIEW_ONLY_V1' AND project_ref='kkxdftdojvnsjqlrulpb') THEN
  RAISE EXCEPTION 'DEDICATED_PREVIEW_SCOPE_REQUIRED';
 END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS aura_preview_signals;
REVOKE ALL ON SCHEMA aura_preview_signals FROM PUBLIC,anon,authenticated;
GRANT USAGE ON SCHEMA aura_preview_signals TO service_role;
CREATE TABLE IF NOT EXISTS aura_preview_signals.push_config (
 id boolean PRIMARY KEY DEFAULT true CHECK(id), value jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS aura_preview_signals.push_subscriptions (
 id text PRIMARY KEY CHECK(id ~ '^[a-f0-9]{64}$'), target jsonb NOT NULL,
 candidate boolean NOT NULL DEFAULT false, watch boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 last_status text, last_at timestamptz
);
CREATE TABLE IF NOT EXISTS aura_preview_signals.push_deliveries (
 id text PRIMARY KEY, subscription_id text NOT NULL, payload jsonb NOT NULL,
 status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','SENDING','SENT','RETRY','EXPIRED','GONE')),
 attempts int NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
 expires_at timestamptz NOT NULL, next_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 lease text, lease_until timestamptz, completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS push_delivery_due ON aura_preview_signals.push_deliveries(next_at)
 WHERE status IN ('PENDING','RETRY','SENDING');
CREATE INDEX IF NOT EXISTS push_delivery_subscription ON aura_preview_signals.push_deliveries(subscription_id);
ALTER TABLE aura_preview_signals.push_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE aura_preview_signals.push_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE aura_preview_signals.push_deliveries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON aura_preview_signals.push_config,aura_preview_signals.push_subscriptions,aura_preview_signals.push_deliveries FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON aura_preview_signals.push_config,aura_preview_signals.push_subscriptions,aura_preview_signals.push_deliveries TO service_role;

CREATE OR REPLACE FUNCTION public.aura_preview_push_v1(p_action text,p_data jsonb DEFAULT '{}'::jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE result jsonb; r aura_preview_signals.push_deliveries%ROWTYPE; sid text; stamp timestamptz:=clock_timestamp();
BEGIN
 IF current_user<>'service_role' THEN RAISE EXCEPTION 'OWNER_SERVICE_REQUIRED'; END IF;
 IF jsonb_typeof(p_data) IS DISTINCT FROM 'object' OR octet_length(p_data::text)>12000 THEN RAISE EXCEPTION 'PUSH_INPUT_FORMAT'; END IF;
 IF p_action='config' THEN
  SELECT value INTO result FROM aura_preview_signals.push_config WHERE id=true;
  RETURN result;
 ELSIF p_action='bootstrap' THEN
  IF coalesce(p_data->>'private','') !~ '^[A-Za-z0-9_-]{43}$' OR coalesce(p_data->>'public','') !~ '^[A-Za-z0-9_-]{87}$' THEN RAISE EXCEPTION 'VAPID_FORMAT'; END IF;
  INSERT INTO aura_preview_signals.push_config(id,value) VALUES(true,p_data) ON CONFLICT DO NOTHING;
  SELECT value INTO result FROM aura_preview_signals.push_config WHERE id=true;
  RETURN result;
 ELSIF p_action='subscribe' THEN
  sid:=p_data->>'id';
  IF coalesce(sid,'') !~ '^[a-f0-9]{64}$' OR jsonb_typeof(p_data->'target') IS DISTINCT FROM 'object'
   OR jsonb_typeof(p_data->'candidate') IS DISTINCT FROM 'boolean' OR jsonb_typeof(p_data->'watch') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'SUBSCRIPTION_FORMAT'; END IF;
  PERFORM pg_advisory_xact_lock(63810421);
  IF NOT EXISTS(SELECT 1 FROM aura_preview_signals.push_subscriptions WHERE id=sid)
   AND (SELECT count(*) FROM aura_preview_signals.push_subscriptions)>=20 THEN RAISE EXCEPTION 'SUBSCRIPTION_CAPACITY'; END IF;
  INSERT INTO aura_preview_signals.push_subscriptions(id,target,candidate,watch)
   VALUES(sid,p_data->'target',(p_data->>'candidate')::boolean,(p_data->>'watch')::boolean)
   ON CONFLICT(id) DO UPDATE SET target=excluded.target,candidate=excluded.candidate,watch=excluded.watch,updated_at=stamp;
  RETURN jsonb_build_object('id',sid,'candidate',p_data->'candidate','watch',p_data->'watch');
 ELSIF p_action='preferences' THEN
  IF jsonb_typeof(p_data->'candidate') IS DISTINCT FROM 'boolean' OR jsonb_typeof(p_data->'watch') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'PREFERENCE_FORMAT'; END IF;
  UPDATE aura_preview_signals.push_subscriptions SET candidate=(p_data->>'candidate')::boolean,watch=(p_data->>'watch')::boolean,updated_at=stamp WHERE id=p_data->>'id';
  RETURN jsonb_build_object('updated',FOUND);
 ELSIF p_action='unsubscribe' THEN
  DELETE FROM aura_preview_signals.push_subscriptions WHERE id=p_data->>'id';
  UPDATE aura_preview_signals.push_deliveries SET status='GONE',lease=NULL,lease_until=NULL WHERE subscription_id=p_data->>'id' AND status IN ('PENDING','RETRY','SENDING');
  RETURN jsonb_build_object('removed',true);
 ELSIF p_action='diagnostics' THEN
  SELECT jsonb_build_object('id',id,'candidate',candidate,'watch',watch,'last_status',last_status,'last_at',extract(epoch FROM last_at)) INTO result
   FROM aura_preview_signals.push_subscriptions WHERE id=p_data->>'id';
  RETURN jsonb_build_object('subscription',result,'subscriber_count',(SELECT count(*) FROM aura_preview_signals.push_subscriptions),
   'pending',(SELECT count(*) FROM aura_preview_signals.push_deliveries WHERE status IN ('PENDING','RETRY','SENDING')));
 ELSIF p_action IN ('enqueue','test') THEN
  IF coalesce(p_data->>'event_id','') !~ '^[a-f0-9]{64}$' OR p_data->>'status' NOT IN ('CANDIDATE','WATCH','TEST')
   OR p_data->>'direction' NOT IN ('LONG','SHORT') OR p_data->>'frame' NOT IN ('5m','15m','1h','4h')
   OR (p_data->>'expires_at')::double precision > extract(epoch FROM stamp)+90
   OR (p_data->>'expires_at')::double precision <= extract(epoch FROM stamp) THEN RETURN '{"enqueued":false}'::jsonb; END IF;
  IF p_action='test' THEN
   -- Explicit owner test is capped per device; no signal is created.
   PERFORM pg_advisory_xact_lock(63810422);
   IF EXISTS(SELECT 1 FROM aura_preview_signals.push_deliveries WHERE subscription_id=p_data->>'subscription_id'
    AND payload->>'status'='TEST' AND expires_at>stamp-interval '60 seconds') THEN RETURN '{"enqueued":false,"code":"TEST_RATE_LIMIT"}'::jsonb; END IF;
  END IF;
  INSERT INTO aura_preview_signals.push_deliveries(id,subscription_id,payload,expires_at)
   SELECT (p_data->>'event_id')||':'||(p_data->>'status')||':'||s.id,s.id,p_data-'subscription_id',to_timestamp((p_data->>'expires_at')::double precision)
   FROM aura_preview_signals.push_subscriptions s
   WHERE (p_action='test' AND s.id=p_data->>'subscription_id') OR
    (p_action='enqueue' AND s.created_at<=to_timestamp((p_data->>'at')::double precision)
      AND ((p_data->>'status'='CANDIDATE' AND s.candidate) OR (p_data->>'status'='WATCH' AND s.watch)))
   ON CONFLICT DO NOTHING;
  RETURN '{"enqueued":true}'::jsonb;
 ELSIF p_action='claim' THEN
  UPDATE aura_preview_signals.push_deliveries SET status='EXPIRED',lease=NULL,lease_until=NULL
   WHERE status IN ('PENDING','RETRY','SENDING') AND (expires_at<=stamp OR attempts>=3 AND coalesce(lease_until,stamp)<=stamp);
  SELECT d.* INTO r FROM aura_preview_signals.push_deliveries d JOIN aura_preview_signals.push_subscriptions s ON s.id=d.subscription_id
   WHERE d.expires_at>stamp AND d.attempts<3 AND
    (d.status IN ('PENDING','RETRY') AND d.next_at<=stamp OR d.status='SENDING' AND d.lease_until<=stamp)
    AND (d.payload->>'status'='TEST' OR d.payload->>'status'='CANDIDATE' AND s.candidate OR d.payload->>'status'='WATCH' AND s.watch)
   ORDER BY d.next_at,d.id FOR UPDATE OF d SKIP LOCKED LIMIT 1;
  IF NOT FOUND THEN RETURN NULL; END IF;
  UPDATE aura_preview_signals.push_deliveries SET status='SENDING',attempts=attempts+1,lease=p_data->>'lease',lease_until=stamp+interval '30 seconds' WHERE id=r.id;
  SELECT jsonb_build_object('id',r.id,'payload',r.payload,'target',target) INTO result FROM aura_preview_signals.push_subscriptions WHERE id=r.subscription_id;
  RETURN result;
 ELSIF p_action='complete' THEN
  SELECT * INTO r FROM aura_preview_signals.push_deliveries WHERE id=p_data->>'id' AND lease=p_data->>'lease' AND status='SENDING' FOR UPDATE;
  IF NOT FOUND THEN RETURN '{"updated":false}'::jsonb; END IF;
  IF coalesce(p_data->>'result','') NOT IN ('ACCEPTED_NOT_DEVICE_CONFIRMED','GONE','RETRY','STALE') THEN RAISE EXCEPTION 'DELIVERY_RESULT_FORMAT'; END IF;
  UPDATE aura_preview_signals.push_deliveries SET status=CASE p_data->>'result' WHEN 'ACCEPTED_NOT_DEVICE_CONFIRMED' THEN 'SENT' WHEN 'GONE' THEN 'GONE' WHEN 'STALE' THEN 'EXPIRED' ELSE 'RETRY' END,
   lease=NULL,lease_until=NULL,next_at=stamp+make_interval(secs=>5*r.attempts),completed_at=stamp WHERE id=r.id;
  UPDATE aura_preview_signals.push_subscriptions SET last_status=p_data->>'result',last_at=stamp WHERE id=r.subscription_id;
  IF p_data->>'result'='GONE' THEN
   DELETE FROM aura_preview_signals.push_subscriptions WHERE id=r.subscription_id;
   UPDATE aura_preview_signals.push_deliveries SET status='GONE',lease=NULL,lease_until=NULL WHERE subscription_id=r.subscription_id AND status IN ('PENDING','RETRY','SENDING');
  END IF;
  RETURN '{"updated":true}'::jsonb;
 ELSIF p_action='cleanup' THEN
  DELETE FROM aura_preview_signals.push_deliveries WHERE expires_at<stamp-interval '7 days';
  RETURN '{"cleaned":true}'::jsonb;
 END IF;
 RAISE EXCEPTION 'PUSH_ACTION_FORBIDDEN';
END $$;
REVOKE ALL ON FUNCTION public.aura_preview_push_v1(text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.aura_preview_push_v1(text,jsonb) TO service_role;
COMMIT;

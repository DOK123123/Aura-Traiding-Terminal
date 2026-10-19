-- Optional additive READ-ONLY history RPC. No balance/position/schema reset.
-- Apply manually as owner, after the existing auto42_schema.sql installation.
BEGIN;
CREATE INDEX IF NOT EXISTS aura_auto42_closed_history
 ON public.aura_auto42_events(epoch,seq DESC) WHERE kind='CLOSE';
CREATE OR REPLACE FUNCTION public.aura_auto42_closed_trades(
 selected_epoch text,before_seq bigint DEFAULT NULL,row_limit integer DEFAULT 50)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=public,pg_temp AS $$
DECLARE result jsonb;
BEGIN
 IF selected_epoch IS NULL OR row_limit IS NULL OR row_limit NOT BETWEEN 1 AND 200 THEN
  RETURN jsonb_build_object('error','WRITE_LIMIT');
 END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY seq DESC),'[]'::jsonb) INTO result
 FROM (SELECT seq,payload,sha256 FROM public.aura_auto42_events
       WHERE epoch=selected_epoch AND kind='CLOSE'
         AND (before_seq IS NULL OR seq<before_seq)
       ORDER BY seq DESC LIMIT row_limit) t;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.aura_auto42_closed_trades(text,bigint,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.aura_auto42_closed_trades(text,bigint,integer) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;

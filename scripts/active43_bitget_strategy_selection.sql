-- Additive owner-mediated strategy selection for the existing Bitget PAPER account.
-- Never calls load/initializes/reset accounts; ordinary commit remains unchanged.
BEGIN;
CREATE OR REPLACE FUNCTION public.aura_active43_bitget_select_strategy(expected_revision bigint,new_state jsonb,new_event jsonb,operation_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,extensions,pg_temp AS $$
DECLARE r public.aura_active43_bitget_account;s jsonb;old_s jsonb;e jsonb;receipt jsonb;
 allowed text[]:=ARRAY['config','config_hash','strategy_change_id','last_error','last_decision','recovery_status','watermark','last_bar_hash','last_mark_at','last_success_at','last_price','last_signal','last_check','production_cycle','signal_evidence','open_evidence','monitor_error'];
 choices jsonb:= '[{"strategy":"DONCHIAN","timeframe":"15m","parameters":{"entry_channel":20,"exit_channel":10,"atr_period":14,"sl_atr":2,"tp_atr":4},"version":"AURA_4.3_ACTIVE_PAPER_3","protocol_hash":"f2bf45afdd0e7fc324afd1c4977376aacd804d02fc6f9494212fc05e45b61e69"},{"strategy":"SR_BOUNCE","timeframe":"5m","parameters":{"level_bars":48,"atr_period":14,"touch_atr":"0.15","penetration_atr":"0.5","sl_atr":"1.5","wick_buffer_atr":"0.25","reward_risk":"1.5"},"version":"AURA_4.3_ACTIVE_PAPER_3","protocol_hash":"19dabf1474387eb6b9ea722b4f8cb9bdc2b1cb00d89a15568362f43bbd4767b3"}]'::jsonb;
BEGIN
 SELECT * INTO r FROM public.aura_active43_bitget_account WHERE id=1 FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','CORRUPT_PORTFOLIO'); END IF;
 old_s:=r.payload::jsonb;s:=(new_state->>'payload')::jsonb;e:=(new_event->>'payload')::jsonb;
 IF operation_key IS NULL OR operation_key !~ '^active43:bitget:strategy:[a-f0-9]{32}$'
  OR new_state->>'sha256' IS DISTINCT FROM encode(extensions.digest(convert_to(new_state->>'payload','UTF8'),'sha256'),'hex')
  OR r.sha256 IS DISTINCT FROM encode(extensions.digest(convert_to(r.payload,'UTF8'),'sha256'),'hex')
  OR s->>'scope' IS DISTINCT FROM 'AURA43_ACTIVE_PAPER'
  OR NOT coalesce(s->'config' IN (choices->0,choices->1),false) OR NOT coalesce(old_s->'config' IN (choices->0,choices->1),false)
  OR s->>'config_hash' IS DISTINCT FROM (CASE WHEN s->'config'=choices->0 THEN 'ed508a541500a2e388f202ea17b122a7aba3429011895ff005e3429a4c114cf7' ELSE '34a7b05d300aeeedf9023b9e40be696a45969b6fa58499f3203d5d09a4221e60' END)
  THEN RETURN jsonb_build_object('error','CONFIG_CHANGED'); END IF;
 SELECT payload::jsonb INTO receipt FROM public.aura_active43_bitget_events WHERE id=operation_key;
 IF FOUND THEN
  IF receipt->>'kind' IS DISTINCT FROM 'STRATEGY_CHANGE' OR receipt->'payload'->'config' IS DISTINCT FROM s->'config'
   OR old_s->'config' IS DISTINCT FROM s->'config' THEN RETURN jsonb_build_object('error','IDEMPOTENCY_CONFLICT'); END IF;
  RETURN jsonb_build_object('revision',r.revision,'payload',r.payload,'sha256',r.sha256,'last_saved_at',floor(extract(epoch FROM r.saved_at))::bigint,'duplicate',true);
 END IF;
 IF expected_revision IS DISTINCT FROM r.revision THEN RETURN jsonb_build_object('error','CONCURRENT_UPDATE'); END IF;
 IF old_s->>'mode' IS DISTINCT FROM 'OFF' OR old_s->'position' IS DISTINCT FROM 'null'::jsonb
  OR old_s->'pending' IS DISTINCT FROM 'null'::jsonb OR old_s->'pending_exit' IS DISTINCT FROM 'null'::jsonb
  OR old_s->'data_recovery_armed' IS DISTINCT FROM 'false'::jsonb OR old_s->'emergency' IS DISTINCT FROM 'false'::jsonb
  OR old_s->>'balance' IS NULL OR old_s->>'day_start_equity' IS NULL OR old_s->>'day_low_equity' IS NULL OR old_s->>'max_drawdown_pct' IS NULL
  OR (old_s->>'balance')::numeric<=0 OR (old_s->>'day_start_equity')::numeric<=0
  OR (old_s->>'day_low_equity')::numeric<=(old_s->>'day_start_equity')::numeric*.98
  OR (old_s->>'max_drawdown_pct')::numeric>=10 THEN RETURN jsonb_build_object('error','STRATEGY_SWITCH_BLOCKED'); END IF;
 -- Financial state, epoch, policy, positions, risk counters and history cannot change.
 IF (s-allowed) IS DISTINCT FROM (old_s-allowed)
  OR s->>'strategy_change_id' IS DISTINCT FROM operation_key
  OR s->'config'=old_s->'config' OR s->>'last_decision' IS DISTINCT FROM 'STRATEGY_CHANGED'
  OR s->>'recovery_status' IS DISTINCT FROM 'STRATEGY_CHANGED_OFF' OR s->'last_error' IS DISTINCT FROM 'null'::jsonb
  OR EXISTS(SELECT 1 FROM unnest(ARRAY['watermark','last_bar_hash','last_mark_at','last_success_at','last_price','last_signal','last_check','production_cycle','signal_evidence','open_evidence','monitor_error']) k WHERE s->k IS DISTINCT FROM 'null'::jsonb)
  THEN RETURN jsonb_build_object('error','STRATEGY_SWITCH_BLOCKED'); END IF;
 IF octet_length(new_state->>'payload')>65536 OR octet_length(new_event->>'payload')>65536
  OR new_event->>'sha256' IS DISTINCT FROM encode(extensions.digest(convert_to(new_event->>'payload','UTF8'),'sha256'),'hex')
  OR new_event->>'id' IS DISTINCT FROM operation_key OR e->>'id' IS DISTINCT FROM operation_key
  OR new_event->>'epoch' IS DISTINCT FROM s->>'epoch' OR e->>'epoch' IS DISTINCT FROM s->>'epoch'
  OR new_event->>'kind' IS DISTINCT FROM 'STRATEGY_CHANGE' OR e->>'kind' IS DISTINCT FROM 'STRATEGY_CHANGE'
  OR new_event->'created_at' IS DISTINCT FROM e->'created_at'
  OR abs(public.aura_active43_bitget_now()-(e->>'created_at')::bigint)>120
  OR e->'payload'->'config' IS DISTINCT FROM s->'config'
  OR e->'payload'->>'scope' IS DISTINCT FROM 'AURA43_ACTIVE_PAPER'
  OR e->'payload'->>'execution_mode' IS DISTINCT FROM 'PAPER_ONLY'
  OR e->'payload'->>'real_money_execution' IS DISTINCT FROM 'DISABLED'
  THEN RETURN jsonb_build_object('error','INVALID_EVENT'); END IF;
 INSERT INTO public.aura_active43_bitget_events(id,epoch,kind,created_at,payload,sha256)
 VALUES(operation_key,s->>'epoch','STRATEGY_CHANGE',(e->>'created_at')::bigint,new_event->>'payload',new_event->>'sha256');
 UPDATE public.aura_active43_bitget_account SET revision=revision+1,payload=new_state->>'payload',sha256=new_state->>'sha256',saved_at=clock_timestamp() WHERE id=1 RETURNING * INTO r;
 RETURN jsonb_build_object('revision',r.revision,'payload',r.payload,'sha256',r.sha256,'last_saved_at',floor(extract(epoch FROM r.saved_at))::bigint,'duplicate',false);
EXCEPTION WHEN data_exception OR integrity_constraint_violation OR raise_exception THEN RETURN jsonb_build_object('error','INVALID_EVENT');
END $$;
REVOKE ALL ON FUNCTION public.aura_active43_bitget_select_strategy(bigint,jsonb,jsonb,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.aura_active43_bitget_select_strategy(bigint,jsonb,jsonb,text) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;

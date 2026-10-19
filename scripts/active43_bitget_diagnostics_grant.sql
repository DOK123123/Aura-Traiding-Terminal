-- OPTIONAL: only if diagnostics reports STORAGE_PERMISSION_DENIED on account GET.
-- Existing Supabase projects normally already grant service_role this SELECT.
-- No reset, seed, row write, trading function replacement, or cross-portfolio grant.
BEGIN;
GRANT SELECT ON TABLE public.aura_active43_bitget_account TO service_role;
NOTIFY pgrst, 'reload schema';
COMMIT;

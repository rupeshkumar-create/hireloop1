-- Test inserts and manual rows use the column default; retire apify as default.

ALTER TABLE public.jobs ALTER COLUMN source SET DEFAULT 'manual';

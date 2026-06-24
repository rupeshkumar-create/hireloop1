-- ============================================================
-- Migration 001 — Enable Postgres extensions
-- ============================================================
-- Run order: first — all other migrations depend on these.

-- pgvector: cosine similarity search for embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Scheduled jobs (purge soft-deleted rows, pg_cron tasks)
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- HTTP calls from DB (e.g. webhook notifications)
CREATE EXTENSION IF NOT EXISTS pg_net;

-- Full-text search (job search, candidate search)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Better statistics
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

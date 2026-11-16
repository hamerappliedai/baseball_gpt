-- Runs once, when the Postgres volume is first created.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- spelling-tolerant player search (phase 4)

-- Layers of the warehouse:
--   raw      CSVs loaded as-is (all text), owned by the pipeline's load step
--   staging  cleaned, typed views (dbt, phase 2)
--   marts    the tables Claude is allowed to query (dbt, phase 2)
--   vectors  embeddings (phase 4)
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;
CREATE SCHEMA IF NOT EXISTS vectors;

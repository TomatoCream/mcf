-- PostgreSQL schema for MCF job crawler

-- Crawl runs table
CREATE TABLE IF NOT EXISTS crawl_runs (
  run_id TEXT PRIMARY KEY,
  started_at TIMESTAMP WITH TIME ZONE,
  finished_at TIMESTAMP WITH TIME ZONE,
  kind TEXT,
  categories_json TEXT,
  total_seen INTEGER,
  added INTEGER,
  maintained INTEGER,
  removed INTEGER
);

-- Jobs table
CREATE TABLE IF NOT EXISTS jobs (
  job_uuid TEXT PRIMARY KEY,
  first_seen_run_id TEXT,
  last_seen_run_id TEXT,
  is_active BOOLEAN,
  first_seen_at TIMESTAMP WITH TIME ZONE,
  last_seen_at TIMESTAMP WITH TIME ZONE,
  title TEXT,
  company_name TEXT,
  location TEXT,
  description TEXT,
  raw_json JSONB
);

-- Job run status table
CREATE TABLE IF NOT EXISTS job_run_status (
  run_id TEXT,
  job_uuid TEXT,
  status TEXT,
  PRIMARY KEY (run_id, job_uuid)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(is_active);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_crawl_runs_finished ON crawl_runs(finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_run_status_run ON job_run_status(run_id);
CREATE INDEX IF NOT EXISTS idx_job_run_status_job ON job_run_status(job_uuid);

-- expdeploy Supabase schema. Idempotent.

CREATE SCHEMA IF NOT EXISTS expdeploy;

CREATE TABLE IF NOT EXISTS expdeploy.runs (
  run_id TEXT PRIMARY KEY,
  exp_id TEXT NOT NULL,
  exp_version TEXT,
  subject_id TEXT NOT NULL,
  session_num TEXT,
  run_num TEXT,
  battery_id TEXT,
  group_index INTEGER,
  started_at TIMESTAMPTZ NOT NULL,
  ended_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  trials_json JSONB DEFAULT '[]'::jsonb,
  interaction_data_json JSONB DEFAULT '[]'::jsonb,
  jspsych_version TEXT,
  deploy_version TEXT,
  client_user_agent TEXT,
  inserted_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_runs_subject ON expdeploy.runs(subject_id, session_num, run_num);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON expdeploy.runs(started_at);

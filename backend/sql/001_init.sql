CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

DO $$ BEGIN
  CREATE TYPE recording_status AS ENUM
  ('uploaded','transcribing','transcribed','summarizing','indexing','ready','failed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE recording_source AS ENUM ('upload','web_record');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recordings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT,
  source recording_source NOT NULL DEFAULT 'upload',
  s3_bucket TEXT NOT NULL,
  s3_key TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  duration_ms INT,
  status recording_status NOT NULL DEFAULT 'uploaded',
  progress SMALLINT NOT NULL DEFAULT 0,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recordings_user_created ON recordings(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS transcripts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recording_id UUID UNIQUE NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  language TEXT,
  full_text TEXT NOT NULL,
  segments JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS summaries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recording_id UUID UNIQUE NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  summary_md TEXT NOT NULL,
  action_items JSONB NOT NULL DEFAULT '[]'::jsonb,
  keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
  timeline JSONB NOT NULL DEFAULT '[]'::jsonb,
  model_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transcript_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recording_id UUID NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  transcript_id UUID NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
  chunk_index INT NOT NULL,
  start_ms INT NOT NULL,
  end_ms INT NOT NULL,
  content TEXT NOT NULL,
  token_count INT,
  embedding vector(1536) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(recording_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_chunks_recording ON transcript_chunks(recording_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON transcript_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE IF NOT EXISTS qa_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recording_id UUID NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  citations JSONB NOT NULL,
  model_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_qa_recording_created ON qa_messages(recording_id, created_at ASC);

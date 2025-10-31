-- 01_schema.sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS deals (
  deal_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived'))
);

CREATE TABLE IF NOT EXISTS documents (
  document_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  deal_id UUID NOT NULL REFERENCES deals(deal_id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  kind TEXT CHECK (kind IN ('pdf','xlsx','txt','pptx','docx','csv')),
  version TEXT,
  sha256 CHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  section TEXT,
  text TEXT NOT NULL,
  page_from INT,
  page_to INT,
  access_tag TEXT DEFAULT 'internal',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS embeddings (
  chunk_id UUID PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  vector VECTOR(768) NOT NULL
);

CREATE TABLE IF NOT EXISTS tables_norm (
  table_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
  name TEXT,
  sheet TEXT,
  note TEXT
);

CREATE TABLE IF NOT EXISTS table_cells (
  cell_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  table_id UUID NOT NULL REFERENCES tables_norm(table_id) ON DELETE CASCADE,
  row_idx INT NOT NULL,
  col_idx INT NOT NULL,
  label TEXT,
  period DATE,
  value NUMERIC,
  unit TEXT,
  currency TEXT,
  source_ref TEXT
);

CREATE TABLE IF NOT EXISTS kpis (
  kpi_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT UNIQUE NOT NULL,
  description TEXT
);

CREATE TABLE IF NOT EXISTS kpi_values (
  kpi_value_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  kpi_id UUID NOT NULL REFERENCES kpis(kpi_id) ON DELETE CASCADE,
  deal_id UUID NOT NULL REFERENCES deals(deal_id) ON DELETE CASCADE,
  as_of DATE NOT NULL,
  value NUMERIC NOT NULL,
  unit TEXT,
  formula TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kpi_value_sources (
  kpi_value_id UUID NOT NULL REFERENCES kpi_values(kpi_value_id) ON DELETE CASCADE,
  source_type TEXT NOT NULL CHECK (source_type IN ('cell','chunk')),
  source_id UUID NOT NULL,
  PRIMARY KEY (kpi_value_id, source_type, source_id)
);

CREATE TABLE IF NOT EXISTS golden_facts (
  gf_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  kpi_id UUID NOT NULL REFERENCES kpis(kpi_id) ON DELETE CASCADE,
  deal_id UUID NOT NULL REFERENCES deals(deal_id) ON DELETE CASCADE,
  kpi_value_id UUID NOT NULL REFERENCES kpi_values(kpi_value_id) ON DELETE CASCADE,
  ttl_until TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'approved' CHECK (status IN ('draft','approved','expired'))
);

CREATE TABLE IF NOT EXISTS runs (
  run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  deal_id UUID NOT NULL REFERENCES deals(deal_id) ON DELETE CASCADE,
  recipe TEXT NOT NULL,
  model TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS outputs (
  output_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  run_id UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('docx','pdf','markdown','json')),
  uri TEXT,
  summary TEXT
);

CREATE TABLE IF NOT EXISTS output_citations (
  output_id UUID NOT NULL REFERENCES outputs(output_id) ON DELETE CASCADE,
  anchor TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK (source_type IN ('cell','chunk','kpi_value')),
  source_id UUID NOT NULL,
  PRIMARY KEY (output_id, anchor, source_type, source_id)
);

CREATE TABLE IF NOT EXISTS calc_cards (
  calc_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  output_id UUID NOT NULL REFERENCES outputs(output_id) ON DELETE CASCADE,
  kpi_value_id UUID NOT NULL REFERENCES kpi_values(kpi_value_id) ON DELETE CASCADE,
  formula TEXT,
  inputs JSONB,
  note TEXT
);

CREATE TABLE IF NOT EXISTS policies (
  policy_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT UNIQUE NOT NULL,
  rules JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS acls (
  acl_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  subject TEXT NOT NULL,
  object_kind TEXT NOT NULL,
  object_id UUID NOT NULL,
  permission TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
  tag TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS object_tags (
  object_kind TEXT NOT NULL,
  object_id UUID NOT NULL,
  tag TEXT NOT NULL REFERENCES tags(tag) ON DELETE CASCADE,
  PRIMARY KEY (object_kind, object_id, tag)
);

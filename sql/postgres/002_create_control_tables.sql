CREATE TABLE IF NOT EXISTS raw._etl_runs (
    batch_id UUID PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    source_system TEXT NOT NULL CHECK (source_system IN ('magento', 'ativo')),
    source_table TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('FULL', 'INCREMENTAL', 'RECONCILIATION', 'SNAPSHOT')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    rows_extracted BIGINT NOT NULL DEFAULT 0 CHECK (rows_extracted >= 0),
    rows_loaded BIGINT NOT NULL DEFAULT 0 CHECK (rows_loaded >= 0),
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS raw._etl_watermark (
    pipeline_name TEXT NOT NULL,
    source_system TEXT NOT NULL CHECK (source_system IN ('magento', 'ativo')),
    source_table TEXT NOT NULL,
    strategy TEXT NOT NULL,
    watermark_column TEXT,
    watermark_value TEXT,
    last_success_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pipeline_name, source_system, source_table)
);

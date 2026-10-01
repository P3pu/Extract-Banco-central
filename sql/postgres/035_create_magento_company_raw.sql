CREATE TABLE IF NOT EXISTS raw.magento_company (
    id BIGINT PRIMARY KEY,
    root_group_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL,
    legal_name VARCHAR(255),
    email VARCHAR(100) NOT NULL,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

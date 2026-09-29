CREATE TABLE IF NOT EXISTS raw.magento_customer (
    entity_id BIGINT PRIMARY KEY,
    group_id INTEGER NOT NULL,
    firstname VARCHAR(255),
    lastname VARCHAR(255),
    email VARCHAR(255),
    dob TEXT,
    taxvat VARCHAR(50),
    gender INTEGER,
    created_at TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

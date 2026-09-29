CREATE TABLE IF NOT EXISTS raw.magento_product (
    entity_id BIGINT PRIMARY KEY,
    sku VARCHAR(64),
    type_id VARCHAR(32) NOT NULL,
    attribute_set_id INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.magento_product_varchar (
    value_id INTEGER PRIMARY KEY,
    attribute_id INTEGER NOT NULL,
    store_id INTEGER NOT NULL,
    entity_id BIGINT NOT NULL,
    value VARCHAR(255),
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

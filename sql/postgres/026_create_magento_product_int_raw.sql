CREATE TABLE IF NOT EXISTS raw.magento_product_int (
    value_id INTEGER PRIMARY KEY,
    attribute_id INTEGER NOT NULL,
    store_id INTEGER NOT NULL,
    entity_id BIGINT NOT NULL,
    value INTEGER,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

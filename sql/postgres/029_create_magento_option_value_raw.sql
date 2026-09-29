CREATE TABLE IF NOT EXISTS raw.magento_option_value (
    value_id BIGINT PRIMARY KEY,
    option_id BIGINT NOT NULL,
    store_id INTEGER NOT NULL,
    value VARCHAR(255),
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

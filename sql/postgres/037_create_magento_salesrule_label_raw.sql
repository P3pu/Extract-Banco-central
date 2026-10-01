CREATE TABLE IF NOT EXISTS raw.magento_salesrule_label (
    label_id BIGINT PRIMARY KEY,
    rule_id BIGINT NOT NULL,
    store_id INTEGER NOT NULL,
    label VARCHAR(255),
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

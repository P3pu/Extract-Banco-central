CREATE TABLE IF NOT EXISTS raw.magento_product_link (
    link_id BIGINT PRIMARY KEY,
    product_id BIGINT NOT NULL,
    linked_product_id BIGINT NOT NULL,
    link_type_id INTEGER NOT NULL,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

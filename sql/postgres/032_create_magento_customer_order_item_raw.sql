CREATE TABLE IF NOT EXISTS raw.magento_customer_order_item (
    id BIGINT PRIMARY KEY,
    sales_order_item_item_id INTEGER,
    customer_id INTEGER,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.magento_eav_attribute (
    attribute_id INTEGER PRIMARY KEY,
    attribute_code VARCHAR(255) NOT NULL,
    backend_type VARCHAR(8) NOT NULL,
    frontend_input VARCHAR(50),
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

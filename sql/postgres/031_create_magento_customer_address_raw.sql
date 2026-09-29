CREATE TABLE IF NOT EXISTS raw.magento_customer_address (
    entity_id BIGINT PRIMARY KEY,
    parent_id BIGINT,
    telephone VARCHAR(255) NOT NULL,
    city VARCHAR(255) NOT NULL,
    region VARCHAR(255),
    region_id BIGINT,
    street TEXT NOT NULL,
    postcode VARCHAR(255),
    country_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.magento_company_user (
    customer_id BIGINT PRIMARY KEY,
    company_id BIGINT NOT NULL,
    is_root INTEGER NOT NULL,
    status INTEGER NOT NULL,
    company_group_id BIGINT NOT NULL,
    company_role_id BIGINT NOT NULL,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

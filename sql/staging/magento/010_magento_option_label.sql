-- Grão: uma linha por option_id; validar unicidade antes de usar como N:1.
CREATE OR REPLACE VIEW staging.magento_option_label AS
SELECT option_id, value AS label, store_id, value_id
FROM raw.magento_option_value
WHERE store_id = 0;

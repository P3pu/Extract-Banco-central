-- O contrato RAW Magento permite item_id=0. Preservar o alerta com o ID real.
-- Migração apenas CORE, atômica com seu registro em schema_migration.
ALTER TABLE core.core_alerta_qualidade
    DROP CONSTRAINT core_alerta_qualidade_identificador_origem_check;
ALTER TABLE core.core_alerta_qualidade
    ADD CONSTRAINT core_alerta_qualidade_identificador_origem_check
    CHECK (identificador_origem >= 0);

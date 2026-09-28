-- Migra a primeira versão da RAW sem descartar a tabela ou os registros.
-- CHAR(1) do PostgreSQL armazena '' como espaço; o cast para TEXT restaura ''
-- porque remove o preenchimento à direita de CHAR(n).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'raw' AND table_name = 'ativo_pedido_evento'
          AND column_name = 'fl_amigo' AND data_type = 'character'
    ) THEN
        ALTER TABLE raw.ativo_pedido_evento
            ALTER COLUMN fl_amigo TYPE VARCHAR(1) USING fl_amigo::TEXT;
    END IF;
END
$$;

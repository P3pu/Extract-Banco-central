-- CORE V1: dados pessoais em dim_pessoa, nunca nos fatos ou logs.
-- Aplicar como migracao separada, em transacao, com registro em
-- core.schema_migration. A tabela permanece restrita ao proprietario/grants
-- explicitos; nao conceder acesso BI por heranca.
ALTER TABLE core.dim_pessoa
    ADD COLUMN cpf TEXT,
    ADD COLUMN nome TEXT,
    ADD COLUMN email TEXT;

COMMENT ON COLUMN core.dim_pessoa.cpf IS
    'CPF/documento conforme cadastro de origem; nao implica CPF valido.';
COMMENT ON COLUMN core.dim_pessoa.nome IS
    'Nome cadastral de origem; dado pessoal de acesso restrito.';
COMMENT ON COLUMN core.dim_pessoa.email IS
    'Email cadastral de origem; dado pessoal de acesso restrito.';

REVOKE ALL ON core.dim_pessoa, core.pessoa_source_map FROM PUBLIC;

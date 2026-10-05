-- Grão: uma linha por usuario_balcao_id; entidade separada de ativo_usuario.
CREATE OR REPLACE VIEW staging.ativo_usuario_balcao AS
SELECT id_usuario AS usuario_balcao_id,
       NULLIF(BTRIM(ds_nome), '') AS nome,
       NULLIF(BTRIM(fl_sexo), '') AS sexo_codigo,
       NULLIF(BTRIM(nr_documento), '') AS documento,
       dt_nascimento AS data_nascimento,
       NULLIF(LOWER(BTRIM(ds_email)), '') AS email,
       NULLIF(BTRIM(ds_telefone), '') AS telefone,
       NULLIF(BTRIM(ds_celular), '') AS celular,
       NULLIF(BTRIM(pelotao), '') AS pelotao,
       dt_cadastro AS data_cadastro,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_usuario_balcao;

-- Grão: uma linha por usuario_id; datas zero permanecem como texto.
CREATE OR REPLACE VIEW staging.ativo_usuario AS
SELECT id_usuario AS usuario_id,
       NULLIF(BTRIM(ds_nome), '') AS nome,
       NULLIF(BTRIM(ds_sobrenome), '') AS sobrenome,
       NULLIF(BTRIM(fl_sexo), '') AS sexo_codigo,
       NULLIF(BTRIM(nr_documento), '') AS documento,
       dt_nascimento AS data_nascimento,
       NULLIF(LOWER(BTRIM(ds_email)), '') AS email,
       NULLIF(BTRIM(nr_telefone), '') AS telefone,
       NULLIF(BTRIM(nr_celular), '') AS celular,
       NULLIF(BTRIM(ds_cep), '') AS cep,
       NULLIF(BTRIM(ds_endereco), '') AS endereco,
       nr_numero AS numero,
       NULLIF(BTRIM(ds_complemento), '') AS complemento,
       NULLIF(BTRIM(ds_bairro), '') AS bairro,
       id_cidade AS cidade_id, id_pais AS pais_id_bruto,
       pelotao, ds_categoria_balcao, nm_necessidades_especiais,
       data_create AS data_criacao, data_update,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_usuario;

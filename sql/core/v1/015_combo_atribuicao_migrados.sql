-- Combos vendidos no Ativo e migrados ao Magento (decisão de negócio 30/10/2026).
-- Cada pedido Magento "<id_pedido Ativo>-<n>" é uma prova de um combo; o
-- prefixo do SKU do bundle até "COMBO<n>" identifica o combo. A inscrição
-- oficial é a do Ativo: liga-se à prova migrada do mesmo pedido Ativo e do
-- mesmo evento, só quando o casamento é 1:1. Um pedido Ativo pode ter vários
-- combos. Escopo: pedidos Ativo informados ou derivados dos pedidos Magento
-- informados; NULL nos dois arrays processa todos.
WITH escopo_magento AS (
    SELECT p.pedido_id_origem, split_part(p.protocolo,'-',1)::bigint ativo_pedido
    FROM core.fato_pedido p
    WHERE p.origem='magento' AND p.protocolo ~ '^[0-9]{9}-[0-9]{1,2}$'
      AND (%(todos)s
           OR p.pedido_id_origem=ANY(%(magento_pedidos)s::bigint[])
           OR split_part(p.protocolo,'-',1)::bigint=ANY(%(ativo_pedidos)s::bigint[]))
), escopo AS (
    SELECT DISTINCT ativo_pedido FROM escopo_magento
    UNION
    SELECT unnest(%(ativo_pedidos)s::bigint[])
), unidades AS (
    SELECT p.ativo_pedido, f.evento_key,
           substring(f.sku_inscricao_magento from '^(.*?COMBO[0-9]*)') combo_sku
    FROM core.fato_pedido mp
    JOIN escopo_magento p ON p.pedido_id_origem=mp.pedido_id_origem
    JOIN core.fato_inscricao f
      ON f.origem='magento' AND f.pedido_id_origem=mp.pedido_id_origem
    WHERE mp.origem='magento'
), combos AS (
    INSERT INTO core.dim_combo (origem, combo_id_origem, nome_combo)
    SELECT DISTINCT 'magento', combo_sku, combo_sku
    FROM unidades WHERE combo_sku IS NOT NULL
    ON CONFLICT (origem, combo_id_origem) DO NOTHING
    RETURNING combo_key, combo_id_origem
), combo_keys AS (
    SELECT combo_key, combo_id_origem FROM combos
    UNION
    SELECT c.combo_key, c.combo_id_origem FROM core.dim_combo c
    WHERE c.origem='magento'
      AND c.combo_id_origem IN (SELECT combo_sku FROM unidades)
), ativo AS (
    SELECT f.inscricao_key, f.pedido_id_origem ativo_pedido, f.evento_key
    FROM core.fato_inscricao f
    WHERE f.origem='ativo' AND f.pedido_id_origem IN (SELECT ativo_pedido FROM escopo)
), pares AS (
    SELECT a.inscricao_key, a.ativo_pedido, u.combo_sku,
           count(*) OVER (PARTITION BY a.inscricao_key) por_inscricao,
           count(*) OVER (PARTITION BY u.ativo_pedido, u.evento_key, u.combo_sku) por_unidade
    FROM ativo a
    JOIN unidades u ON u.ativo_pedido=a.ativo_pedido AND u.evento_key=a.evento_key
    WHERE u.combo_sku IS NOT NULL AND a.evento_key IS NOT NULL
), desejadas AS (
    SELECT p.inscricao_key, k.combo_key,
           p.ativo_pedido::text || ':' || p.combo_sku grupo_comercial_id
    FROM pares p JOIN combo_keys k ON k.combo_id_origem=p.combo_sku
    WHERE p.por_inscricao=1 AND p.por_unidade=1
), removidas AS (
    DELETE FROM core.combo_inscricao_atribuicao t
    USING ativo a
    WHERE t.inscricao_key=a.inscricao_key
      AND t.grupo_comercial_id LIKE '%%:%%COMBO%%'
      -- Troca de combo é feita pelo ON CONFLICT; aqui só sai quem deixou de casar.
      AND NOT EXISTS (SELECT 1 FROM desejadas d
                      WHERE d.inscricao_key=t.inscricao_key)
    RETURNING 1
)
INSERT INTO core.combo_inscricao_atribuicao
    (inscricao_key, combo_key, grupo_comercial_id, validado_por, validado_em)
SELECT inscricao_key, combo_key, grupo_comercial_id,
       %(validado_por)s, %(validado_em)s::timestamptz
FROM desejadas
ON CONFLICT (inscricao_key) DO UPDATE SET
    combo_key=EXCLUDED.combo_key,
    grupo_comercial_id=EXCLUDED.grupo_comercial_id,
    validado_por=EXCLUDED.validado_por,
    validado_em=EXCLUDED.validado_em
WHERE (core.combo_inscricao_atribuicao.combo_key,
       core.combo_inscricao_atribuicao.grupo_comercial_id)
      IS DISTINCT FROM (EXCLUDED.combo_key, EXCLUDED.grupo_comercial_id);

-- Um registro por combo vendido, sem dupla contagem (decisão 03/11/2026):
-- * Ativo (oficial para o que foi vendido no Ativo): unidade =
--   grupo_comercial_id de combo_inscricao_atribuicao (regra 016);
--   valores = soma das inscrições Ativo do combo; migrado_magento só sinaliza;
--   qtd_provas_combo = quantidade mais comum de inscrições daquele combo;
--   revisar_tamanho = inscrições acima dela sem formar outro combo.
-- * Magento direto: unidade = bundle com COMBO no SKU fora dos protocolos
--   migrados; provas = número de COMBO<n>.
-- Não substitui a view de indicadores. No Ativo, o combo conta se qualquer
-- inscrição contar: foi vendido mesmo com uma prova cancelada (decisão 03/11/2026).
CREATE OR REPLACE VIEW core.combo_vendido AS
WITH migrados AS (
    SELECT DISTINCT split_part(p.protocolo,'-',1)::bigint AS ativo_pedido
    FROM core.fato_pedido p
    WHERE p.origem='magento' AND p.protocolo ~ '^[0-9]{9}-[0-9]{1,2}$'
), ativo AS (
    SELECT a.grupo_comercial_id AS combo_vendido_id,
           'ATIVO' AS canal_venda,
           BOOL_OR(m.ativo_pedido IS NOT NULL) AS migrado_magento,
           a.combo_key, c.origem AS combo_origem, c.combo_id_origem AS combo_codigo,
           c.nome_combo,
           MIN(f.pedido_id_origem) AS pedido_id_origem,
           MIN(p.data_pedido) AS data_pedido,
           COUNT(*) AS qtd_inscricoes,
           SUM(f.valor_bruto_inscricao) AS valor_bruto,
           CASE WHEN BOOL_AND(f.valor_liquido_inscricao IS NOT NULL)
                THEN SUM(f.valor_liquido_inscricao) END AS valor_liquido,
           CASE WHEN BOOL_OR(f.contabiliza_inscricao IS TRUE) THEN TRUE
                WHEN BOOL_AND(f.contabiliza_inscricao IS FALSE) THEN FALSE END AS contabiliza,
           CASE WHEN BOOL_AND(f.estado_derivacao='VALIDADO') THEN 'VALIDADO'
                ELSE 'PENDENTE' END AS estado_derivacao
    FROM core.combo_inscricao_atribuicao a
    JOIN core.fato_inscricao f ON f.inscricao_key=a.inscricao_key AND f.origem='ativo'
    JOIN core.dim_combo c ON c.combo_key=a.combo_key
    LEFT JOIN core.fato_pedido p ON p.pedido_key=f.pedido_key
    LEFT JOIN migrados m ON m.ativo_pedido=f.pedido_id_origem
    GROUP BY a.grupo_comercial_id, a.combo_key, c.origem, c.combo_id_origem, c.nome_combo
), tamanho AS (
    SELECT combo_key, mode() WITHIN GROUP (ORDER BY qtd_inscricoes)::integer AS tamanho
    FROM ativo GROUP BY combo_key
), magento AS (
    SELECT 'magento:' || f.inscricao_id_origem AS combo_vendido_id,
           'MAGENTO' AS canal_venda,
           FALSE AS migrado_magento,
           NULL::bigint AS combo_key, 'magento' AS combo_origem,
           substring(f.sku_inscricao_magento from '^(.*?COMBO[0-9]*)') AS combo_codigo,
           substring(f.sku_inscricao_magento from '^(.*?COMBO[0-9]*)') AS nome_combo,
           f.pedido_id_origem, p.data_pedido,
           1::bigint AS qtd_inscricoes,
           NULLIF(substring(f.sku_inscricao_magento from 'COMBO([0-9]+)'),'')::integer
             AS qtd_provas_combo,
           f.valor_bruto_inscricao AS valor_bruto,
           f.valor_liquido_inscricao AS valor_liquido,
           f.contabiliza_inscricao AS contabiliza,
           f.estado_derivacao,
           FALSE AS revisar_tamanho
    FROM core.fato_inscricao f
    LEFT JOIN core.fato_pedido p ON p.pedido_key=f.pedido_key
    WHERE f.origem='magento' AND f.sku_inscricao_magento ~* 'COMBO'
      AND f.motivo_elegibilidade IS DISTINCT FROM 'COMBO_MIGRADO_ATIVO'
)
SELECT a.combo_vendido_id, a.canal_venda, a.migrado_magento, a.combo_key,
       a.combo_origem, a.combo_codigo, a.nome_combo, a.pedido_id_origem,
       a.data_pedido, a.qtd_inscricoes, t.tamanho AS qtd_provas_combo,
       a.valor_bruto, a.valor_liquido, a.contabiliza, a.estado_derivacao,
       a.qtd_inscricoes>t.tamanho AS revisar_tamanho
FROM ativo a JOIN tamanho t ON t.combo_key=a.combo_key
UNION ALL
SELECT * FROM magento;

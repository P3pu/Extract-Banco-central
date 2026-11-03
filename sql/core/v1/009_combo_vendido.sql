-- Um registro por combo vendido, sem dupla contagem (decisão 03/11/2026):
-- * Ativo (oficial para o que foi vendido no Ativo): unidade =
--   grupo_comercial_id de combo_inscricao_atribuicao (regra 016);
--   valores = soma das inscrições Ativo do combo; migrado_magento só sinaliza;
--   qtd_provas_combo = quantidade mais comum de inscrições daquele combo.
-- * Magento direto, fora dos protocolos migrados: cada linha é uma prova e cada
--   etapa costuma vir em um pedido, sem participante. Unidade = comprador +
--   circuito + COMBO<n> do primeiro trecho do SKU (CDE25SP1COMBO4 = circuito
--   CDE25SP, etapa 1, 4 provas); a k-ésima linha de cada etapa forma o k-ésimo
--   combo. O Hoodie vem dentro do SKU e não tem linha própria.
-- Não substitui a view de indicadores. O combo conta se qualquer inscrição
-- contar: foi vendido mesmo com uma prova cancelada, mas o valor das canceladas
-- não entra nos valores do combo.
-- revisar = combo que contaria, mas fica fora da contagem até ser revisto.
-- motivo_revisao, separados por +:
--   TAMANHO: inscrições acima do tamanho sem formar outro combo;
--   VALOR: inscrição não cancelada acima de R$ 2.000 (combos 408 e 437 de 2017);
--   PRODUTO: evento em core.evento_revisao (Kit Vip);
--   SEM_NUMERO: SKU Magento sem COMBO<n>;
--   ETAPAS_INCOMPLETAS: circuito Magento com menos etapas que provas no SKU
--   (ex.: CDE24SP1COMBO2, em que a outra prova tem outro SKU);
--   SEM_COMPRADOR: linha Magento que não dá para agrupar.
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
           COALESCE(SUM(f.valor_bruto_inscricao)
                    FILTER (WHERE f.flag_cancelado_inscricao IS NOT TRUE),0) AS valor_bruto,
           CASE WHEN COALESCE(BOOL_AND(f.valor_liquido_inscricao IS NOT NULL)
                              FILTER (WHERE f.flag_cancelado_inscricao IS NOT TRUE),TRUE)
                THEN COALESCE(SUM(f.valor_liquido_inscricao)
                              FILTER (WHERE f.flag_cancelado_inscricao IS NOT TRUE),0)
                END AS valor_liquido,
           COALESCE(MAX(f.valor_bruto_inscricao)
                    FILTER (WHERE f.flag_cancelado_inscricao IS NOT TRUE),0)>2000 AS valor_suspeito,
           BOOL_OR(x.evento_id_origem IS NOT NULL) AS produto_em_revisao,
           CASE WHEN BOOL_OR(f.contabiliza_inscricao IS TRUE) THEN TRUE
                WHEN BOOL_AND(f.contabiliza_inscricao IS FALSE) THEN FALSE END AS contabiliza,
           CASE WHEN BOOL_AND(f.estado_derivacao='VALIDADO') THEN 'VALIDADO'
                ELSE 'PENDENTE' END AS estado_derivacao
    FROM core.combo_inscricao_atribuicao a
    JOIN core.fato_inscricao f ON f.inscricao_key=a.inscricao_key AND f.origem='ativo'
    JOIN core.dim_combo c ON c.combo_key=a.combo_key
    LEFT JOIN core.fato_pedido p ON p.pedido_key=f.pedido_key
    LEFT JOIN migrados m ON m.ativo_pedido=f.pedido_id_origem
    LEFT JOIN core.evento_revisao x ON x.evento_id_origem=f.evento_id_origem
    GROUP BY a.grupo_comercial_id, a.combo_key, c.origem, c.combo_id_origem, c.nome_combo
), tamanho AS (
    SELECT combo_key, mode() WITHIN GROUP (ORDER BY qtd_inscricoes)::integer AS tamanho
    FROM ativo GROUP BY combo_key
), ativo_revisao AS (
    SELECT a.*, t.tamanho,
           CASE WHEN a.contabiliza IS NOT FALSE THEN NULLIF(concat_ws('+',
                CASE WHEN a.qtd_inscricoes>t.tamanho THEN 'TAMANHO' END,
                CASE WHEN a.valor_suspeito THEN 'VALOR' END,
                CASE WHEN a.produto_em_revisao THEN 'PRODUTO' END),'') END AS motivo_revisao
    FROM ativo a JOIN tamanho t ON t.combo_key=a.combo_key
), magento_linhas AS (
    SELECT f.inscricao_key, f.pedido_id_origem, p.data_pedido, f.valor_bruto_inscricao,
           f.valor_liquido_inscricao, f.flag_cancelado_inscricao, f.contabiliza_inscricao,
           f.estado_derivacao,
           p.comprador_id_origem IS NULL AS sem_comprador,
           COALESCE(p.comprador_id_origem::text,'pedido' || f.pedido_id_origem::text) AS comprador,
           regexp_replace(s.trecho,'[0-9]?COMBO.*$','') AS circuito,
           substring(s.trecho from '([0-9])COMBO') AS etapa,
           substring(s.trecho from 'COMBO([0-9]+)$')::integer AS provas
    FROM core.fato_inscricao f
    CROSS JOIN LATERAL (SELECT split_part(f.sku_inscricao_magento,'-',1) AS trecho) s
    LEFT JOIN core.fato_pedido p ON p.pedido_key=f.pedido_key
    WHERE f.origem='magento' AND f.sku_inscricao_magento ~* 'COMBO'
      AND f.motivo_elegibilidade IS DISTINCT FROM 'COMBO_MIGRADO_ATIVO'
), magento_etapas AS (
    SELECT circuito, provas, COUNT(DISTINCT etapa) AS etapas
    FROM magento_linhas GROUP BY circuito, provas
), magento_ordem AS (
    -- Canceladas por último: compra refeita não mistura etapas canceladas e válidas.
    SELECT l.*,
           row_number() OVER (PARTITION BY l.comprador, l.circuito, l.provas, l.etapa
                              ORDER BY l.flag_cancelado_inscricao IS TRUE, l.inscricao_key) AS ordem,
           COUNT(*) OVER (PARTITION BY l.comprador, l.circuito, l.provas) AS linhas_compra
    FROM magento_linhas l
), magento AS (
    SELECT 'magento:' || o.comprador || ':' || o.circuito || ':'
             || COALESCE(o.provas::text,'sem_numero') || ':' || o.ordem::text AS combo_vendido_id,
           o.circuito, o.provas, o.linhas_compra, o.sem_comprador, e.etapas,
           MIN(o.pedido_id_origem) AS pedido_id_origem,
           MIN(o.data_pedido) AS data_pedido,
           COUNT(*) AS qtd_inscricoes,
           COALESCE(SUM(o.valor_bruto_inscricao)
                    FILTER (WHERE o.flag_cancelado_inscricao IS NOT TRUE),0) AS valor_bruto,
           CASE WHEN COALESCE(BOOL_AND(o.valor_liquido_inscricao IS NOT NULL)
                              FILTER (WHERE o.flag_cancelado_inscricao IS NOT TRUE),TRUE)
                THEN COALESCE(SUM(o.valor_liquido_inscricao)
                              FILTER (WHERE o.flag_cancelado_inscricao IS NOT TRUE),0)
                END AS valor_liquido,
           CASE WHEN BOOL_OR(o.contabiliza_inscricao IS TRUE) THEN TRUE
                WHEN BOOL_AND(o.contabiliza_inscricao IS FALSE) THEN FALSE END AS contabiliza,
           CASE WHEN BOOL_AND(o.estado_derivacao='VALIDADO') THEN 'VALIDADO'
                ELSE 'PENDENTE' END AS estado_derivacao
    FROM magento_ordem o
    JOIN magento_etapas e ON e.circuito=o.circuito AND e.provas IS NOT DISTINCT FROM o.provas
    GROUP BY o.comprador, o.circuito, o.provas, o.ordem, o.linhas_compra, o.sem_comprador, e.etapas
), magento_revisao AS (
    SELECT g.*,
           CASE WHEN g.contabiliza IS NOT FALSE THEN NULLIF(concat_ws('+',
                CASE WHEN g.provas IS NULL THEN 'SEM_NUMERO' END,
                CASE WHEN g.linhas_compra>g.provas AND g.linhas_compra % g.provas<>0 THEN 'TAMANHO' END,
                CASE WHEN g.etapas<g.provas THEN 'ETAPAS_INCOMPLETAS' END,
                CASE WHEN g.sem_comprador THEN 'SEM_COMPRADOR' END),'') END AS motivo_revisao
    FROM magento g
)
SELECT r.combo_vendido_id, r.canal_venda, r.migrado_magento, r.combo_key,
       r.combo_origem, r.combo_codigo, r.nome_combo, r.pedido_id_origem,
       r.data_pedido, r.qtd_inscricoes, r.tamanho AS qtd_provas_combo,
       r.valor_bruto, r.valor_liquido,
       CASE WHEN r.motivo_revisao IS NOT NULL THEN FALSE ELSE r.contabiliza END AS contabiliza,
       r.estado_derivacao,
       r.motivo_revisao IS NOT NULL AS revisar,
       r.motivo_revisao
FROM ativo_revisao r
UNION ALL
SELECT r.combo_vendido_id, 'MAGENTO', FALSE, NULL::bigint,
       'magento', r.circuito || 'COMBO' || COALESCE(r.provas::text,''),
       r.circuito || 'COMBO' || COALESCE(r.provas::text,''), r.pedido_id_origem,
       r.data_pedido, r.qtd_inscricoes, r.provas,
       r.valor_bruto, r.valor_liquido,
       CASE WHEN r.motivo_revisao IS NOT NULL THEN FALSE ELSE r.contabiliza END,
       r.estado_derivacao,
       r.motivo_revisao IS NOT NULL,
       r.motivo_revisao
FROM magento_revisao r;

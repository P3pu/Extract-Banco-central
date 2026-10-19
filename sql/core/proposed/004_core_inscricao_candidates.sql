-- PROPOSTA FASE B v1: SELECTs DE TRANSFORMAÇÃO, SOMENTE LEITURA.
-- NÃO EXECUTAR nesta fase; as fontes auxiliares ainda não foram integradas.
-- NÃO PROMOVER A UPSERT SEM APROVAR DEPENDÊNCIAS E TESTAR EM HOMOLOGAÇÃO.
-- :id_min / :id_max delimitam pedido_id para incluir todos os bundles do pedido.
-- Esta escolha impede conciliar um pedido com apenas parte das inscrições.

-- Magento: pré-agrega filhos por pai, depois agrega a soma identificada por
-- pedido. Um desconto só no header fica em desconto_nao_atribuido, sem rateio.
WITH pais AS MATERIALIZED (
    SELECT i.*, item.quantidade_pedida, item.quantidade_cancelada,
           item.quantidade_reembolsada, item.desconto AS desconto_pai
    FROM staging.magento_inscricao i
    JOIN staging.magento_item_pedido item ON item.item_id = i.inscricao_id
    WHERE i.pedido_id BETWEEN :id_min AND :id_max
), filhos AS (
    SELECT p.inscricao_id,
           COUNT(c.componente_item_id) AS qtd_filhos,
           COUNT(c.desconto) AS qtd_descontos_preenchidos,
           SUM(c.desconto) AS desconto_filhos
    FROM pais p
    LEFT JOIN staging.magento_bundle_componente c
      ON c.inscricao_item_id = p.inscricao_id
    GROUP BY p.inscricao_id
), base AS (
    SELECT p.*, f.qtd_filhos, f.qtd_descontos_preenchidos,
           f.desconto_filhos,
           CASE WHEN f.desconto_filhos > 0 THEN f.desconto_filhos
                WHEN p.desconto_pai IS NOT NULL THEN p.desconto_pai
                WHEN f.qtd_filhos > 0 AND f.qtd_descontos_preenchidos = f.qtd_filhos
                     THEN 0::NUMERIC END AS desconto_aplicado,
           fp.pedido_key, fp.status_corporativo, fp.pagamento_confirmado,
           fp.desconto_pedido_origem,
           em.evento_key, de.flag_evento_teste
    FROM pais p
    JOIN filhos f ON f.inscricao_id = p.inscricao_id
    LEFT JOIN core.fato_pedido fp
      ON fp.origem = 'magento' AND fp.pedido_id_origem = p.pedido_id
    LEFT JOIN core.evento_source_map em
      ON em.origem = 'magento' AND em.evento_id_origem = p.evento_id
    LEFT JOIN core.dim_evento de ON de.evento_key = em.evento_key
), conciliacao AS (
    SELECT pedido_id,
           SUM(desconto_aplicado) AS desconto_itens_identificado,
           COUNT(*) FILTER (WHERE desconto_aplicado IS NULL) AS itens_desconto_desconhecido,
           COUNT(*) FILTER (WHERE quantidade_pedida IS DISTINCT FROM 1
                             OR quantidade_reembolsada > 0
                             OR (quantidade_cancelada > 0
                                 AND quantidade_cancelada < quantidade_pedida))
               AS itens_quantidade_excepcional
    FROM base GROUP BY pedido_id
)
SELECT b.pedido_id, b.inscricao_id, b.pedido_key, b.evento_id,
       b.evento_key, b.categoria_origem::TEXT AS categoria_id_origem,
       NULL::TEXT AS categoria_nome_origem,
       b.valor_bruto AS valor_bruto_inscricao,
       b.desconto_filhos, b.desconto_pai, b.desconto_aplicado,
       CASE WHEN b.valor_bruto IS NOT NULL AND b.desconto_aplicado IS NOT NULL
            THEN b.valor_bruto - b.desconto_aplicado END AS valor_liquido_itens,
       CASE WHEN b.desconto_pedido_origem IS NOT NULL
                 AND c.itens_desconto_desconhecido = 0
            THEN ABS(b.desconto_pedido_origem) - c.desconto_itens_identificado
            END AS desconto_nao_atribuido_pedido,
       CASE WHEN b.desconto_pedido_origem IS NULL
                 OR c.itens_desconto_desconhecido > 0
                 OR c.itens_quantidade_excepcional > 0
                 OR ABS(ABS(b.desconto_pedido_origem)
                        - c.desconto_itens_identificado) > 0.0001
            THEN NULL::NUMERIC
            WHEN b.quantidade_pedida = 1 AND COALESCE(b.quantidade_cancelada,0) = 0
                 AND COALESCE(b.quantidade_reembolsada,0) = 0
                 THEN b.valor_bruto - b.desconto_aplicado
            END AS valor_liquido_inscricao_candidato,
       b.quantidade_pedida, b.quantidade_cancelada, b.quantidade_reembolsada,
       b.flag_evento_teste,
       b.evento_key IS NULL AS evento_nao_mapeado,
       b.status_corporativo,
       CASE WHEN b.quantidade_pedida > 0
                 AND b.quantidade_cancelada >= b.quantidade_pedida THEN TRUE
            WHEN b.quantidade_pedida = 1
                 AND COALESCE(b.quantidade_cancelada,0) = 0 THEN FALSE
            ELSE NULL END AS cancelamento_individual,
       CASE WHEN b.status_corporativo IN ('CANCELADO','INDETERMINADO')
                 OR b.flag_evento_teste IS DISTINCT FROM FALSE
                 OR b.quantidade_pedida IS DISTINCT FROM 1
                 OR COALESCE(b.quantidade_reembolsada,0) > 0
                 OR COALESCE(b.quantidade_cancelada,0) > 0
            THEN FALSE
            WHEN b.pagamento_confirmado IS TRUE THEN TRUE
            ELSE FALSE END AS pagamento_confirmado_inscricao,
       CASE WHEN b.status_corporativo IN ('NOVO','PENDENTE')
                 AND b.data_evento::DATE < CURRENT_DATE
                 AND b.flag_evento_teste IS FALSE
                 AND b.quantidade_pedida = 1
                 AND COALESCE(b.quantidade_cancelada,0) = 0
                 AND COALESCE(b.quantidade_reembolsada,0) = 0
            THEN TRUE ELSE FALSE END AS pagamento_presumido_candidato
FROM base b
JOIN conciliacao c ON c.pedido_id = b.pedido_id;

-- PENDÊNCIAS Magento antes do UPSERT:
-- 1) descontos de itens raiz não-bundle e linhas sem desconto informado;
-- 2) 66 bundles qty !=1 e cancelamento/reembolso parcial;
-- 3) pedido misto evento teste/real ou evento sem mapa não pode receber header
--    integral como valor comercial de um subconjunto;
-- 4) mapeamento de participante e categoria textual continuam NULL.

-- Ativo: conversões e sinais sem junção 1:N. Requer a view proposta de
-- cabeçalho cupom; sem ela a classificação completa fica pendente.
SELECT i.pedido_id, i.inscricao_id, fp.pedido_key,
       i.evento_id, em.evento_key, i.usuario_id AS participante_id_origem,
       i.status_detalhado_id, sd.descricao AS status_individual_origem,
       sd.tipo AS tipo_status_detalhado,
       i.preco AS valor_bruto_inscricao,
       i.desconto_individual AS desconto_individual_original,
       core.try_numeric_20_4(i.desconto_individual) AS desconto_individual,
       cat.valor_kit AS valor_kit_ativo,
       CASE WHEN i.preco IS NOT NULL
                 AND core.try_numeric_20_4(i.desconto_individual) IS NOT NULL
                 AND cat.valor_kit IS NOT NULL
            THEN GREATEST(0, i.preco
                              - core.try_numeric_20_4(i.desconto_individual)
                              - cat.valor_kit) END AS valor_liquido_inscricao_candidato,
       i.taxa AS taxa_servico_ativo,
       i.categoria, i.modalidade, i.tamanho_camiseta,
       cupom.codigo_cupom, cab.classificacao AS classificacao_cupom,
       CASE WHEN cab.classificacao ILIKE '%grupos%'
                 OR i.categoria ILIKE '%grupo%'
                 OR i.categoria ILIKE '%saúde corporativa%'
                 OR cupom.codigo_cupom ~* '^GR' THEN 'Grupos'
            WHEN i.categoria ILIKE '%cortesia%'
                 OR i.categoria ILIKE '%patrocinador%'
                 OR i.preco = 0 THEN 'Cortesia'
            WHEN cab.cupom_desconto_id IS NOT NULL THEN 'Site'
            ELSE NULL END AS classificacao_candidata,
       fp.status_corporativo,
       CASE WHEN fp.status_corporativo = 'CANCELADO'
                 OR i.status_detalhado_id IN (5,6,7,8) THEN FALSE
            WHEN i.status_detalhado_id = 0
                 AND (i.status_pedido_id = 2
                      OR (i.status_pedido_id = 1
                          AND i.local_inscricao_codigo = 2))
                 AND em.evento_key IS NOT NULL
                 AND de.flag_evento_teste IS FALSE THEN TRUE
            ELSE NULL END AS contabiliza_inscricao_candidata,
       CASE WHEN fp.status_corporativo = 'CANCELADO'
                 OR i.status_detalhado_id IN (5,6,7,8) THEN FALSE
            WHEN i.status_detalhado_id = 0
                 AND i.status_pedido_id = 2
                 AND de.flag_evento_teste IS FALSE THEN TRUE
            ELSE FALSE END AS pagamento_confirmado_inscricao,
       CASE WHEN i.status_detalhado_id = 0
                 AND fp.status_corporativo IN ('PENDENTE','NOVO')
                 AND core.try_date(i.data_evento) < CURRENT_DATE
                 AND de.flag_evento_teste IS FALSE
                 AND i.pedido_mapeado THEN TRUE
            ELSE FALSE END AS pagamento_presumido_candidato,
       NOT i.pedido_mapeado AS pedido_nao_encontrado,
       em.evento_key IS NULL AS evento_nao_mapeado,
       CASE WHEN i.desconto_individual IS NOT NULL
                 AND core.try_numeric_20_4(i.desconto_individual) IS NULL
            THEN 'DESCONTO_INVALIDO' END AS erro_desconto,
       CASE WHEN i.data_evento IS NOT NULL
                 AND core.try_date(i.data_evento) IS NULL
            THEN 'DATA_EVENTO_INVALIDA' END AS erro_data_evento
FROM staging.ativo_inscricao i
LEFT JOIN core.fato_pedido fp
  ON fp.origem = 'ativo' AND fp.pedido_id_origem = i.pedido_id
LEFT JOIN core.evento_source_map em
  ON em.origem = 'ativo' AND em.evento_id_origem = i.evento_id
LEFT JOIN core.dim_evento de ON de.evento_key = em.evento_key
LEFT JOIN staging.ativo_categoria cat ON cat.categoria_id = i.categoria_id
LEFT JOIN staging.ativo_cupom cupom ON cupom.cupom_id = i.cupom_individual_id
LEFT JOIN staging.ativo_cupom_desconto cab
  ON cab.cupom_desconto_id = cupom.cupom_desconto_id
LEFT JOIN staging.ativo_status_detalhado sd
  ON sd.status_detalhado_id = i.status_detalhado_id
WHERE i.pedido_id BETWEEN :id_min AND :id_max;

-- O INSERT ... ON CONFLICT de fato_inscricao fica retido nesta versão. Ainda
-- falta resolver os gates acima e demonstrar que os SELECTs resultam exatamente
-- em uma linha por (origem,inscricao_id_origem). Quando aprovado, usar
-- ON CONFLICT(origem,inscricao_id_origem) DO UPDATE com hash dos campos
-- derivados, incluindo CURRENT_DATE/pagamento_presumido, e nunca DELETE por
-- ausência em um lote. O motivo desta retenção é evitar materializar como
-- definitivo um líquido ou status individual incorreto.

-- PROPOSTA FASE B v1. NÃO EXECUTAR. Revisar e testar em homologação primeiro.
-- Faixa inclusiva definida por core.id_min/core.id_max na sessão; executar UM bloco
-- por origem/entidade dentro de uma transação de lote. Não usar para toda a
-- história em uma transação. Requer 001, 002 e dependências de 000 aprovadas.
-- O orquestrador futuro deve validar id_min <= id_max, serializar por lock,
-- registrar core_etl_execucao e retornar contagens por INSERT/UPDATE.

-- ETAPA 1A: dimensão/evento e source_map, sem união automática entre origens.
BEGIN;
CREATE TEMP TABLE core_lote_eventos ON COMMIT DROP AS
SELECT 'ativo'::TEXT AS origem, evento_id::BIGINT AS evento_id_origem,
       evento_nome AS nome_evento, core.try_date(data_evento) AS data_evento,
       data_evento AS data_evento_original,
       campanha_salesforce_id AS sku_origem,
       evento_id = 22054 AS flag_evento_teste
FROM staging.ativo_evento WHERE evento_id BETWEEN core.batch_min() AND core.batch_max()
UNION ALL
SELECT 'magento', evento_id::BIGINT, evento_nome, data_evento::DATE,
       data_evento::TEXT, evento_sku, FALSE
FROM staging.magento_evento WHERE evento_id BETWEEN core.batch_min() AND core.batch_max();
CREATE UNIQUE INDEX ON core_lote_eventos(origem, evento_id_origem);

INSERT INTO core.dim_evento
    (seed_origem, seed_evento_id, nome_evento, data_evento,
     data_evento_original, sku_referencia, flag_evento_teste, motivo_evento_teste)
SELECT origem, evento_id_origem, nome_evento, data_evento,
       data_evento_original, sku_origem, flag_evento_teste,
       CASE WHEN flag_evento_teste THEN 'CURADORIA_ATIVO_22054' END
FROM core_lote_eventos
ON CONFLICT (seed_origem, seed_evento_id) DO UPDATE SET
    nome_evento = EXCLUDED.nome_evento,
    data_evento = EXCLUDED.data_evento,
    data_evento_original = EXCLUDED.data_evento_original,
    sku_referencia = EXCLUDED.sku_referencia,
    flag_evento_teste = EXCLUDED.flag_evento_teste,
    motivo_evento_teste = EXCLUDED.motivo_evento_teste,
    data_atualizacao_core = clock_timestamp()
WHERE (core.dim_evento.nome_evento, core.dim_evento.data_evento,
       core.dim_evento.data_evento_original, core.dim_evento.sku_referencia,
       core.dim_evento.flag_evento_teste)
  IS DISTINCT FROM
      (EXCLUDED.nome_evento, EXCLUDED.data_evento,
       EXCLUDED.data_evento_original, EXCLUDED.sku_referencia,
       EXCLUDED.flag_evento_teste);

INSERT INTO core.evento_source_map
    (origem, evento_id_origem, evento_key, sku_origem, criterio_vinculo)
SELECT s.origem, s.evento_id_origem, d.evento_key, s.sku_origem, 'ORIGEM'
FROM core_lote_eventos s
JOIN core.dim_evento d
  ON d.seed_origem = s.origem AND d.seed_evento_id = s.evento_id_origem
ON CONFLICT (origem, evento_id_origem) DO UPDATE SET
    sku_origem = EXCLUDED.sku_origem
WHERE core.evento_source_map.criterio_vinculo = 'ORIGEM'
  AND core.evento_source_map.sku_origem IS DISTINCT FROM EXCLUDED.sku_origem;
COMMIT;

-- ETAPA 1B: combo Ativo apenas ID/nome. Magento combo não tem fonte validada.
BEGIN;
INSERT INTO core.dim_combo (origem, combo_id_origem, nome_combo)
SELECT 'ativo', combo_id::TEXT, combo_nome
FROM staging.ativo_combo WHERE combo_id BETWEEN core.batch_min() AND core.batch_max()
ON CONFLICT (origem, combo_id_origem) DO UPDATE SET
    nome_combo = EXCLUDED.nome_combo, atualizado_core_em = clock_timestamp()
WHERE core.dim_combo.nome_combo IS DISTINCT FROM EXCLUDED.nome_combo;
COMMIT;

-- ETAPA 2A: pedidos Magento, cabeçalho 1:1; nenhuma junção a filhos/regras.
BEGIN;
INSERT INTO core.fato_pedido
    (origem, pedido_id_origem, protocolo, comprador_id_origem,
     data_pedido, data_pedido_original, data_atualizacao_origem,
     status_pedido_origem, estado_pedido_origem, status_corporativo,
     flag_cancelado, pagamento_confirmado, valor_bruto_pedido,
     desconto_pedido_origem, valor_liquido_pedido, frete_pedido,
     imposto_pedido, valor_total_cobrado, taxa_adicional_operacional,
     batch_id_origem, conteudo_hash)
SELECT 'magento', p.pedido_id, p.protocolo, p.cliente_id::BIGINT,
       p.criado_em, p.criado_em::TEXT, p.atualizado_em,
       p.status_pedido, p.estado_pedido,
       core.magento_status_corporativo(p.estado_pedido,p.status_pedido),
       LOWER(COALESCE(p.estado_pedido,'')) = 'canceled'
          OR LOWER(COALESCE(p.status_pedido,'')) = 'canceled',
       core.magento_pagamento_confirmado(p.estado_pedido,p.status_pedido),
       p.subtotal, p.desconto,
       CASE WHEN p.subtotal IS NOT NULL AND p.desconto IS NOT NULL
            THEN p.subtotal + p.desconto END,
       p.frete, p.imposto, p.valor_total,
       CASE WHEN p.valor_total IS NOT NULL AND p.subtotal IS NOT NULL
                 AND p.desconto IS NOT NULL
            THEN p.valor_total - (p.subtotal + p.desconto) END,
       p.batch_id,
       md5(ROW(p.pedido_id,p.cliente_id,p.criado_em,p.atualizado_em,
               p.estado_pedido,p.status_pedido,p.subtotal,p.desconto,
               p.frete,p.imposto,p.valor_total)::TEXT)
FROM staging.magento_pedido p
WHERE p.pedido_id BETWEEN core.batch_min() AND core.batch_max()
ON CONFLICT (origem, pedido_id_origem) DO UPDATE SET
    protocolo=EXCLUDED.protocolo, comprador_id_origem=EXCLUDED.comprador_id_origem,
    data_pedido=EXCLUDED.data_pedido, data_pedido_original=EXCLUDED.data_pedido_original,
    data_atualizacao_origem=EXCLUDED.data_atualizacao_origem,
    status_pedido_origem=EXCLUDED.status_pedido_origem,
    estado_pedido_origem=EXCLUDED.estado_pedido_origem,
    status_corporativo=EXCLUDED.status_corporativo,
    flag_cancelado=EXCLUDED.flag_cancelado,
    pagamento_confirmado=EXCLUDED.pagamento_confirmado,
    valor_bruto_pedido=EXCLUDED.valor_bruto_pedido,
    desconto_pedido_origem=EXCLUDED.desconto_pedido_origem,
    valor_liquido_pedido=EXCLUDED.valor_liquido_pedido,
    frete_pedido=EXCLUDED.frete_pedido,
    imposto_pedido=EXCLUDED.imposto_pedido,
    valor_total_cobrado=EXCLUDED.valor_total_cobrado,
    taxa_adicional_operacional=EXCLUDED.taxa_adicional_operacional,
    batch_id_origem=EXCLUDED.batch_id_origem,
    conteudo_hash=EXCLUDED.conteudo_hash,
    atualizado_core_em=clock_timestamp()
WHERE core.fato_pedido.conteudo_hash IS DISTINCT FROM EXCLUDED.conteudo_hash;

-- Alertas têm apenas PK numérica e código controlado. Sem texto de driver/PII.
INSERT INTO core.core_alerta_qualidade
    (batch_id, origem, entidade, identificador_origem, codigo_regra, severidade)
SELECT p.batch_id, 'magento', 'pedido', p.pedido_id,
       core.magento_status_alerta(p.estado_pedido,p.status_pedido), 'WARNING'
FROM staging.magento_pedido p
WHERE p.pedido_id BETWEEN core.batch_min() AND core.batch_max()
  AND core.magento_status_alerta(p.estado_pedido,p.status_pedido) IS NOT NULL
ON CONFLICT DO NOTHING;

UPDATE core.core_alerta_qualidade a
SET ativo=FALSE, resolvido_em=clock_timestamp()
FROM staging.magento_pedido p
WHERE a.origem='magento' AND a.entidade='pedido'
  AND a.identificador_origem=p.pedido_id AND a.ativo
  AND a.codigo_regra IN ('STATUS_CONTRADITORIO','STATUS_ESPECIAL')
  AND p.pedido_id BETWEEN core.batch_min() AND core.batch_max()
  AND a.codigo_regra IS DISTINCT FROM
      core.magento_status_alerta(p.estado_pedido,p.status_pedido);
COMMIT;

-- ETAPA 2B: pedidos Ativo. Totais financeiros permanecem NULL até prova de
-- cobertura completa das inscrições. Comprador depende de 000 + backfill.
BEGIN;
INSERT INTO core.fato_pedido
    (origem, pedido_id_origem, protocolo, comprador_id_origem,
     data_pedido, data_pedido_original, data_atualizacao_origem,
     data_atualizacao_original, status_pedido_origem,
     status_pedido_codigo, local_inscricao_codigo, status_corporativo,
     flag_cancelado, pagamento_confirmado, desconto_pedido_origem,
     batch_id_origem, conteudo_hash)
SELECT 'ativo', p.pedido_id, p.codigo, p.comprador_usuario_id::BIGINT,
       core.try_timestamp(p.data_pedido), p.data_pedido,
       core.try_timestamp(p.data_alteracao), p.data_alteracao,
       p.status, p.status_id, p.local_inscricao_codigo,
       CASE p.status_id WHEN 5 THEN 'CANCELADO' WHEN 2 THEN 'CONFIRMADO'
           WHEN 1 THEN 'PENDENTE' WHEN 6 THEN 'NOVO' ELSE 'INDETERMINADO' END,
       p.status_id = 5,
       CASE WHEN p.status_id = 5 THEN FALSE WHEN p.status_id = 2 THEN TRUE
            WHEN p.status_id IN (1,6) THEN FALSE ELSE NULL END,
       p.desconto, p.batch_id,
       md5(ROW(p.pedido_id,p.comprador_usuario_id,p.data_pedido,
               p.data_alteracao,p.status_id,p.local_inscricao_codigo,
               p.desconto)::TEXT)
FROM staging.ativo_pedido p
WHERE p.pedido_id BETWEEN core.batch_min() AND core.batch_max()
ON CONFLICT (origem, pedido_id_origem) DO UPDATE SET
    protocolo=EXCLUDED.protocolo, comprador_id_origem=EXCLUDED.comprador_id_origem,
    data_pedido=EXCLUDED.data_pedido, data_pedido_original=EXCLUDED.data_pedido_original,
    data_atualizacao_origem=EXCLUDED.data_atualizacao_origem,
    data_atualizacao_original=EXCLUDED.data_atualizacao_original,
    status_pedido_origem=EXCLUDED.status_pedido_origem,
    status_pedido_codigo=EXCLUDED.status_pedido_codigo,
    local_inscricao_codigo=EXCLUDED.local_inscricao_codigo,
    status_corporativo=EXCLUDED.status_corporativo,
    flag_cancelado=EXCLUDED.flag_cancelado,
    pagamento_confirmado=EXCLUDED.pagamento_confirmado,
    desconto_pedido_origem=EXCLUDED.desconto_pedido_origem,
    batch_id_origem=EXCLUDED.batch_id_origem,
    conteudo_hash=EXCLUDED.conteudo_hash,
    atualizado_core_em=clock_timestamp()
WHERE core.fato_pedido.conteudo_hash IS DISTINCT FROM EXCLUDED.conteudo_hash;
COMMIT;

-- ETAPA 3: inscrição, agregados financeiros e alertas exigem os gates de
-- status/composição/identidade descritos em docs/CORE_FASE_B_MODELO.md.
-- Os SELECTs de transformação e os casos conhecidos estão em
-- 004_core_inscricao_candidates.sql. Não promover seus candidatos a fatos
-- sem validar cobertura, performance e precedências em homologação.

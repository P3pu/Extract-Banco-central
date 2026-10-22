-- Somente fontes comprovadas. Cupom de cabeçalho/status detalhado ausentes
-- permanecem pendências; não inferir comprador ou CPF.
WITH dados AS (
    SELECT f.inscricao_key, f.conteudo_hash, f.flag_evento_nao_mapeado,
           f.flag_pedido_nao_encontrado, f.flag_evento_teste, f.data_evento,
           f.combo_key,
           i.status_detalhado_id, i.status_pedido_id,
           i.local_inscricao_codigo, i.preco, i.desconto_individual,
           i.taxa, i.categoria, i.cupom_individual_id,
           p.cupom_desconto_item_id cupom_pedido_id,
           cat.valor_kit, cupom.codigo_cupom,
           dc.flag_composicao_validada,
           dc.qtd_inscricoes_previstas,
           core.try_numeric_20_4(i.desconto_individual) desconto_num,
           (i.status_detalhado_id IN (5,6,7,8)
             OR i.status_pedido_id=5) cancelada,
           (i.status_detalhado_id IN (0,9,10,11,12,13)) status_elegivel,
           (i.status_detalhado_id IS NULL
             OR i.status_detalhado_id NOT IN (0,5,6,7,8,9,10,11,12,13))
             status_pendente,
           (i.status_pedido_id=2 OR
             (i.status_pedido_id=1 AND i.local_inscricao_codigo=2))
             pedido_elegivel,
           (i.categoria ILIKE '%%grupo%%'
             OR i.categoria ILIKE '%%saúde corporativa%%'
             OR i.categoria ILIKE '%%saude corporativa%%') categoria_grupos,
           (i.categoria ILIKE '%%cortesia%%'
             OR i.categoria ILIKE '%%patrocinador%%') categoria_cortesia,
           (BTRIM(cupom.codigo_cupom) ~* '^GR') cupom_gr,
           md5(ROW(f.conteudo_hash,i.status_detalhado_id,i.status_pedido_id,
                   i.local_inscricao_codigo,i.preco,i.desconto_individual,
                   i.taxa,i.categoria,i.cupom_individual_id,
                   p.cupom_desconto_item_id,
                   cat.valor_kit,cupom.codigo_cupom,
                   dc.flag_composicao_validada,
                   dc.qtd_inscricoes_previstas,
                   f.flag_evento_teste,f.flag_evento_nao_mapeado,
                   f.flag_pedido_nao_encontrado,%(as_of_date)s::date,
                   'CORE_V1_20261022')::text) dep_hash
    FROM core.fato_inscricao f
    JOIN staging.ativo_inscricao i
      ON i.inscricao_id=f.inscricao_id_origem
    LEFT JOIN staging.ativo_categoria cat
      ON cat.categoria_id=i.categoria_id
    LEFT JOIN staging.ativo_cupom cupom
      ON cupom.cupom_id=i.cupom_individual_id
    LEFT JOIN staging.ativo_pedido p ON p.pedido_id=i.pedido_id
    LEFT JOIN core.dim_combo dc ON dc.combo_key=f.combo_key
    WHERE f.origem='ativo'
      AND f.inscricao_id_origem BETWEEN %(id_min)s AND %(id_max)s
), regra AS (
    SELECT d.*,
           (COALESCE(categoria_grupos,false) OR COALESCE(cupom_gr,false))
             sinal_grupos,
           (COALESCE(categoria_cortesia,false) OR preco=0)
             sinal_cortesia,
           ((cupom_individual_id IS NOT NULL OR cupom_pedido_id IS NOT NULL)
             AND NOT COALESCE(categoria_grupos,false))
             classificacao_pendente,
           (preco IS NULL OR desconto_num IS NULL OR valor_kit IS NULL
             OR preco<0 OR desconto_num<0 OR valor_kit<0)
             financeiro_pendente
    FROM dados d
), final AS (
    SELECT r.*,
           CASE WHEN cancelada THEN false
                WHEN status_pendente THEN NULL::boolean
                WHEN NOT pedido_elegivel THEN false
                WHEN flag_pedido_nao_encontrado
                  OR flag_evento_nao_mapeado
                  OR flag_evento_teste IS DISTINCT FROM false
                  THEN NULL::boolean
                WHEN status_elegivel THEN true END elegivel,
           CASE WHEN sinal_grupos THEN 'GRUPOS'
                WHEN classificacao_pendente AND NOT COALESCE(cupom_gr,false)
                     THEN NULL::text
                WHEN sinal_cortesia THEN 'CORTESIA'
                ELSE 'SITE' END classe,
           CASE WHEN sinal_grupos AND cupom_gr THEN 'CUPOM_GR'
                WHEN sinal_grupos THEN 'CATEGORIA_GRUPOS'
                WHEN classificacao_pendente THEN 'CUPOM_HEADER_AUSENTE'
                WHEN sinal_cortesia AND categoria_cortesia
                     THEN 'CATEGORIA_CORTESIA'
                WHEN sinal_cortesia THEN 'BRUTO_ZERO'
                ELSE 'SEM_SINAL_ESPECIAL' END motivo_classe
    FROM regra r
)
UPDATE core.fato_inscricao f SET
    flag_cancelado_inscricao=d.cancelada,
    contabiliza_inscricao=d.elegivel,
    contabiliza_bruto=CASE WHEN d.elegivel IS TRUE
                           AND d.financeiro_pendente IS FALSE THEN true
                           WHEN d.elegivel IS FALSE THEN false END,
    pagamento_confirmado=CASE WHEN d.cancelada THEN false
                               WHEN d.elegivel IS TRUE
                                AND d.status_pedido_id=2 THEN true
                               WHEN d.elegivel IS TRUE
                                AND d.status_pedido_id=1
                                AND d.local_inscricao_codigo=2 THEN false
                               WHEN d.elegivel IS FALSE THEN false END,
    pagamento_presumido=false,
    pago_considerado=CASE WHEN d.cancelada THEN false
                          WHEN d.elegivel IS TRUE
                           AND d.status_pedido_id=2 THEN true
                          WHEN d.elegivel IS TRUE
                           AND d.status_pedido_id=1
                           AND d.local_inscricao_codigo=2 THEN false
                          WHEN d.elegivel IS FALSE THEN false END,
    motivo_elegibilidade=CASE WHEN d.cancelada THEN 'CANCELAMENTO_PREVALECE'
                              WHEN d.status_pendente THEN 'STATUS_ESPECIAL'
                              WHEN d.status_pedido_id=1
                               AND d.local_inscricao_codigo=2
                               THEN 'BALCAO_ELEGIVEL_NAO_PAGO_CONFIRMADO'
                              WHEN d.elegivel IS TRUE THEN 'PEDIDO_E_INSCRICAO_ELEGIVEIS'
                              ELSE 'RELACIONAMENTO_OU_STATUS_PENDENTE' END,
    status_pendente_validacao=d.status_pendente,
    motivo_status_analitico=CASE WHEN d.cancelada THEN 'CANCELADA'
                                 WHEN d.status_pendente THEN 'CODIGO_PENDENTE'
                                 WHEN d.elegivel IS TRUE THEN 'ELEGIVEL'
                                 ELSE 'PEDIDO_NAO_ELEGIVEL_OU_SEM_MAPA' END,
    classificacao_comercial=d.classe,
    classificacao_venda=CASE d.classe WHEN 'GRUPOS' THEN 'Grupos'
                                      WHEN 'CORTESIA' THEN 'Cortesia'
                                      WHEN 'SITE' THEN 'Site' END,
    classificacao_incompleta=d.classificacao_pendente AND NOT d.sinal_grupos,
    motivo_classificacao=d.motivo_classe,
    regras_classificacao=jsonb_build_object(
        'cupom_gr',COALESCE(d.cupom_gr,false),
        'categoria_grupos',COALESCE(d.categoria_grupos,false),
        'categoria_cortesia',COALESCE(d.categoria_cortesia,false),
        'cabecalho_cupom_disponivel',false),
    cupom_codigo_origem=d.codigo_cupom,
    classificacao_cupom_ativo=NULL,
    desconto_individual_origem=d.desconto_num,
    valor_kit_ativo=d.valor_kit,
    valor_liquido_inscricao=CASE WHEN d.financeiro_pendente IS FALSE
        THEN GREATEST(0,d.preco-d.desconto_num-d.valor_kit) END,
    valor_bruto_mais_taxa_derivado=CASE WHEN d.preco IS NOT NULL
                                             AND d.taxa IS NOT NULL
        THEN d.preco+d.taxa END,
    taxa_servico_ativo=d.taxa,
    flag_excecao_financeira=d.financeiro_pendente,
    estado_derivacao=CASE WHEN d.financeiro_pendente OR d.status_pendente
                              OR (d.classificacao_pendente AND NOT d.sinal_grupos)
                              OR d.elegivel IS NULL THEN 'PENDENTE'
                          ELSE 'VALIDADO' END,
    derivado_de_hash=f.conteudo_hash,
    dependencias_hash_snapshot=d.dep_hash,
    derivado_de_dependencias_hash=d.dep_hash,
    versao_regras_derivacao='CORE_V1_20261022',
    derivado_em=%(as_of_date)s::date,
    data_referencia_pagamento=%(as_of_date)s::date,
    atualizado_core_em=clock_timestamp()
FROM final d
WHERE f.inscricao_key=d.inscricao_key
  AND (f.dependencias_hash_snapshot IS DISTINCT FROM d.dep_hash
       OR f.derivado_de_hash IS DISTINCT FROM f.conteudo_hash
       OR f.versao_regras_derivacao IS DISTINCT FROM 'CORE_V1_20261022');

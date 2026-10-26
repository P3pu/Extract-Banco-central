WITH fonte AS (
    SELECT p.*,
           core.magento_status_corporativo(p.estado_pedido,p.status_pedido) situacao,
           md5(ROW(p.pedido_id,p.protocolo,p.cliente_id,p.criado_em,
                   p.atualizado_em,p.estado_pedido,p.status_pedido,p.subtotal,
                   p.desconto,p.frete,p.imposto,p.valor_total)::text) hash_novo
    FROM staging.magento_pedido p
    WHERE p.pedido_id BETWEEN %(id_min)s AND %(id_max)s
)
INSERT INTO core.fato_pedido
    (origem,pedido_id_origem,protocolo,comprador_id_origem,
     data_pedido,data_pedido_original,data_atualizacao_origem,
     status_pedido_origem,estado_pedido_origem,status_corporativo,
     flag_cancelado,pedido_elegivel,pagamento_confirmado,
     pagamento_considerado,motivo_status_analitico,
     valor_bruto_pedido,desconto_pedido_origem,valor_liquido_pedido,
     frete_pedido,imposto_pedido,valor_total_cobrado,
     flag_excecao_financeira,batch_id_origem,conteudo_hash)
SELECT 'magento',pedido_id,protocolo,cliente_id::bigint,
       criado_em,criado_em::text,atualizado_em,status_pedido,estado_pedido,
       situacao,situacao='CANCELADO',
       situacao IN ('CONFIRMADO','PENDENTE','NOVO'),
       core.magento_pagamento_confirmado(estado_pedido,status_pedido),
       core.magento_pagamento_confirmado(estado_pedido,status_pedido),
       CASE WHEN situacao='INDETERMINADO' THEN 'STATE_STATUS_NAO_CONCILIADO'
            WHEN situacao='CANCELADO' THEN 'CANCELAMENTO_PREVALECE'
            ELSE situacao END,
       subtotal,desconto,
       CASE WHEN subtotal IS NOT NULL AND desconto IS NOT NULL
            THEN subtotal+desconto END,
       frete,imposto,valor_total,true,batch_id,hash_novo
FROM fonte
ON CONFLICT (origem,pedido_id_origem) DO UPDATE SET
    protocolo=EXCLUDED.protocolo,
    comprador_id_origem=EXCLUDED.comprador_id_origem,
    data_pedido=EXCLUDED.data_pedido,
    data_pedido_original=EXCLUDED.data_pedido_original,
    data_atualizacao_origem=EXCLUDED.data_atualizacao_origem,
    status_pedido_origem=EXCLUDED.status_pedido_origem,
    estado_pedido_origem=EXCLUDED.estado_pedido_origem,
    status_corporativo=EXCLUDED.status_corporativo,
    flag_cancelado=EXCLUDED.flag_cancelado,
    pedido_elegivel=EXCLUDED.pedido_elegivel,
    pagamento_confirmado=EXCLUDED.pagamento_confirmado,
    pagamento_considerado=EXCLUDED.pagamento_considerado,
    motivo_status_analitico=EXCLUDED.motivo_status_analitico,
    valor_bruto_pedido=EXCLUDED.valor_bruto_pedido,
    desconto_pedido_origem=EXCLUDED.desconto_pedido_origem,
    valor_liquido_pedido=EXCLUDED.valor_liquido_pedido,
    frete_pedido=EXCLUDED.frete_pedido,
    imposto_pedido=EXCLUDED.imposto_pedido,
    valor_total_cobrado=EXCLUDED.valor_total_cobrado,
    desconto_itens_identificado=NULL,
    desconto_nao_atribuido=NULL,
    flag_excecao_financeira=true,
    flag_evento_teste=NULL,
    flag_pedido_misto_teste=NULL,
    flag_pedido_misto_temporal=NULL,
    batch_id_origem=EXCLUDED.batch_id_origem,
    conteudo_hash=EXCLUDED.conteudo_hash,
    atualizado_core_em=clock_timestamp()
WHERE core.fato_pedido.conteudo_hash IS DISTINCT FROM EXCLUDED.conteudo_hash;

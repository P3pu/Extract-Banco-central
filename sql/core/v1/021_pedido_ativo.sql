WITH fonte AS (
    SELECT p.*,
           md5(ROW(p.pedido_id,p.data_pedido,p.data_alteracao,p.status_id,
                   p.local_inscricao_codigo,p.desconto)::text) hash_novo
    FROM staging.ativo_pedido p
    WHERE p.pedido_id BETWEEN %(id_min)s AND %(id_max)s
)
INSERT INTO core.fato_pedido
    (origem,pedido_id_origem,protocolo,comprador_id_origem,
     data_pedido,data_pedido_original,data_atualizacao_origem,
     data_atualizacao_original,status_pedido_origem,status_pedido_codigo,
     local_inscricao_codigo,status_corporativo,flag_cancelado,
     pedido_elegivel,pagamento_confirmado,pagamento_considerado,
     motivo_status_analitico,desconto_pedido_origem,batch_id_origem,
     conteudo_hash,flag_excecao_financeira)
SELECT 'ativo',pedido_id,pedido_id::text,NULL::bigint,
       core.try_timestamp(data_pedido),data_pedido,
       core.try_timestamp(data_alteracao),data_alteracao,
       status,status_id,local_inscricao_codigo,
       CASE WHEN status_id=5 THEN 'CANCELADO'
            WHEN status_id=2 THEN 'CONFIRMADO'
            WHEN status_id=1 THEN 'PENDENTE'
            WHEN status_id=6 THEN 'NOVO' ELSE 'INDETERMINADO' END,
       status_id=5,
       status_id=2 OR (status_id=1 AND local_inscricao_codigo=2),
       CASE WHEN status_id=2 THEN TRUE
            WHEN status_id IN (1,5,6) THEN FALSE END,
       CASE WHEN status_id=2 THEN TRUE
            WHEN status_id IN (1,5,6) THEN FALSE END,
       CASE WHEN status_id=1 AND local_inscricao_codigo=2
            THEN 'BALCAO_ELEGIVEL_NAO_COMPROVA_PAGAMENTO'
            WHEN status_id=2 THEN 'STATUS_PAGO'
            WHEN status_id=5 THEN 'CANCELADO'
            ELSE 'STATUS_PENDENTE_VALIDACAO' END,
       desconto,batch_id,hash_novo,true
FROM fonte
ON CONFLICT (origem,pedido_id_origem) DO UPDATE SET
    protocolo=EXCLUDED.protocolo,
    data_pedido=EXCLUDED.data_pedido,
    data_pedido_original=EXCLUDED.data_pedido_original,
    data_atualizacao_origem=EXCLUDED.data_atualizacao_origem,
    data_atualizacao_original=EXCLUDED.data_atualizacao_original,
    status_pedido_origem=EXCLUDED.status_pedido_origem,
    status_pedido_codigo=EXCLUDED.status_pedido_codigo,
    local_inscricao_codigo=EXCLUDED.local_inscricao_codigo,
    status_corporativo=EXCLUDED.status_corporativo,
    flag_cancelado=EXCLUDED.flag_cancelado,
    pedido_elegivel=EXCLUDED.pedido_elegivel,
    pagamento_confirmado=EXCLUDED.pagamento_confirmado,
    pagamento_considerado=EXCLUDED.pagamento_considerado,
    motivo_status_analitico=EXCLUDED.motivo_status_analitico,
    desconto_pedido_origem=EXCLUDED.desconto_pedido_origem,
    valor_bruto_pedido=NULL,
    valor_liquido_pedido=NULL,
    taxa_servico_total_ativo=NULL,
    flag_excecao_financeira=true,
    flag_evento_teste=NULL,
    flag_pedido_misto_teste=NULL,
    batch_id_origem=EXCLUDED.batch_id_origem,
    conteudo_hash=EXCLUDED.conteudo_hash,
    atualizado_core_em=clock_timestamp()
WHERE core.fato_pedido.conteudo_hash IS DISTINCT FROM EXCLUDED.conteudo_hash;

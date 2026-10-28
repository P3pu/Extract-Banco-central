-- Reprocessar os IDs de inscrição impactados em lote supervisionado posterior.
-- Só pedidos alterados nesta transação (o UPSERT 020/021 grava
-- atualizado_core_em apenas quando o hash muda), na mesma origem.
UPDATE core.fato_inscricao f SET estado_derivacao='PENDENTE',
    derivado_de_dependencias_hash=NULL, atualizado_core_em=clock_timestamp()
FROM core.fato_pedido p
WHERE p.origem IN ('ativo','magento') -- usa fato_pedido_origem_uk
  AND p.pedido_id_origem BETWEEN %(id_min)s AND %(id_max)s
  AND p.atualizado_core_em >= now()
  AND f.origem=p.origem
  AND f.pedido_id_origem=p.pedido_id_origem
  AND f.estado_derivacao<>'PENDENTE';

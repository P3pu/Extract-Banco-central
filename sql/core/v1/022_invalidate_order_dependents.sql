-- Reprocessar os IDs de inscrição impactados em lote supervisionado posterior.
UPDATE core.fato_inscricao f SET estado_derivacao='PENDENTE',
    derivado_de_dependencias_hash=NULL, atualizado_core_em=clock_timestamp()
WHERE f.pedido_id_origem BETWEEN %(id_min)s AND %(id_max)s
  AND f.estado_derivacao<>'PENDENTE';

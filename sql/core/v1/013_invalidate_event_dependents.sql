-- Alteração de data, flag de teste ou mapa exige recalcular cada inscrição.
UPDATE core.fato_inscricao f SET estado_derivacao='PENDENTE',
    derivado_de_dependencias_hash=NULL, atualizado_core_em=clock_timestamp()
WHERE f.evento_id_origem BETWEEN %(id_min)s AND %(id_max)s
  AND f.estado_derivacao<>'PENDENTE';

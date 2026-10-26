UPDATE core.fato_inscricao f SET estado_derivacao='PENDENTE',
    derivado_de_dependencias_hash=NULL, atualizado_core_em=clock_timestamp()
FROM core.dim_combo c
WHERE f.combo_key=c.combo_key
  AND c.origem='ativo'
  AND core.try_numeric_20_4(c.combo_id_origem)
      BETWEEN %(id_min)s AND %(id_max)s
  AND f.estado_derivacao<>'PENDENTE';

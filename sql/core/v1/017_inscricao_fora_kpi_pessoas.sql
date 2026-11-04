-- Marca as inscrições que não aparecem em KPIs de pessoa (decisão 04/11/2026).
-- A inscrição e o faturamento seguem contando: só a pessoa não pode ser medida.
-- PENDENTE_VINCULO é temporário: o ciclo diário tenta ligar a pessoa de novo.
CREATE OR REPLACE VIEW core.inscricao_fora_kpi_pessoas AS
SELECT f.inscricao_key, f.origem, f.inscricao_id_origem, f.evento_key, f.data_evento,
       f.contabiliza_inscricao,
       true AS flag_fora_kpi_pessoas,
       CASE WHEN p.pessoa_key IS NOT NULL AND p.cpf_valido IS FALSE THEN 'CPF_INVALIDO'
            WHEN p.pessoa_key IS NOT NULL THEN 'SEM_CPF'
            WHEN f.origem='magento' AND ic.cliente_ambiguo THEN 'CLIENTE_AMBIGUO'
            WHEN f.origem='magento' AND ic.cliente_id IS NULL THEN 'SEM_CLIENTE'
            WHEN f.origem='magento' AND c.cliente_id IS NULL THEN 'CLIENTE_NAO_CARREGADO'
            WHEN f.origem='magento' THEN 'PENDENTE_VINCULO'
            WHEN f.participante_id_origem IS NULL THEN 'SEM_PARTICIPANTE'
            ELSE 'PARTICIPANTE_SEM_CADASTRO' END AS motivo,
       'Esta pessoa não aparece nos KPIs de pessoas'::text AS aviso
FROM core.fato_inscricao f
LEFT JOIN core.dim_pessoa p ON p.pessoa_key=f.participante_key
LEFT JOIN staging.magento_item_cliente ic
  ON f.origem='magento' AND ic.item_id=f.inscricao_id_origem
LEFT JOIN staging.magento_cliente c ON c.cliente_id=ic.cliente_id
WHERE p.pessoa_key IS NULL OR p.criterio_identificacao<>'CPF_VALIDO';

-- Diagnóstico read-only; preencher limites <=100000 IDs antes de executar.
-- Não exporta identificadores pessoais nem consulta CPF/nome/e-mail.
BEGIN READ ONLY;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='2s';
SELECT current_database() banco, current_setting('transaction_read_only') leitura;

-- Substituir os dois UNSET por inteiros aprovados. BETWEEN é inclusivo.
SELECT set_config('core.id_min','UNSET',true);
SELECT set_config('core.id_max','UNSET',true);

SELECT origem,COUNT(*) linhas,COUNT(DISTINCT pedido_id_origem) pedidos
FROM core.fato_pedido
WHERE pedido_id_origem BETWEEN core.batch_min() AND core.batch_max()
GROUP BY origem;

SELECT origem,COUNT(*) inscricoes,
       COUNT(*) FILTER (WHERE flag_pedido_nao_encontrado) orfas,
       COUNT(*) FILTER (WHERE flag_evento_nao_mapeado) sem_evento,
       COUNT(*) FILTER (WHERE estado_derivacao='PENDENTE') pendentes
FROM core.fato_inscricao
WHERE inscricao_id_origem BETWEEN core.batch_min() AND core.batch_max()
GROUP BY origem;

SELECT origem,pedido_id_origem,COUNT(*) duplicadas
FROM core.fato_pedido
WHERE pedido_id_origem BETWEEN core.batch_min() AND core.batch_max()
GROUP BY origem,pedido_id_origem HAVING COUNT(*)>1;

SELECT origem,inscricao_id_origem,COUNT(*) duplicadas
FROM core.fato_inscricao
WHERE inscricao_id_origem BETWEEN core.batch_min() AND core.batch_max()
GROUP BY origem,inscricao_id_origem HAVING COUNT(*)>1;

SELECT p.origem,p.pedido_id_origem,p.valor_bruto_pedido,
       p.desconto_pedido_origem,p.valor_liquido_pedido,
       p.desconto_itens_identificado,p.desconto_nao_atribuido,
       p.flag_excecao_financeira,p.flag_pedido_misto_teste
FROM core.fato_pedido p
WHERE p.origem='magento'
  AND p.pedido_id_origem BETWEEN core.batch_min() AND core.batch_max()
ORDER BY p.pedido_id_origem LIMIT 1000;

SELECT origem,estado_derivacao,COUNT(*)
FROM core.fato_inscricao
WHERE inscricao_id_origem BETWEEN core.batch_min() AND core.batch_max()
GROUP BY origem,estado_derivacao;

-- O gate permanece fechado independentemente da carga.
SELECT COUNT(*) indicadores_publicados
FROM core.fato_inscricao_indicadores_validos;
ROLLBACK;

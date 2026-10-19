-- PROPOSTA FASE B v1. CONSULTAS SOMENTE LEITURA, NÃO EXECUTADAS.
-- Rodar apenas APÓS aprovação, implantação e carga em homologação, cada bloco
-- isolado com statement_timeout baixo. Não usar EXPLAIN ANALYZE em produção.
-- Nunca selecionar CPF/nome/documento ou imprimir dados pessoais.

-- T01/T02: o UNIQUE do DDL deve impedir duplicatas. Zero linhas é sucesso.
SELECT origem, pedido_id_origem, COUNT(*) AS n
FROM core.fato_pedido
GROUP BY origem, pedido_id_origem HAVING COUNT(*) > 1 LIMIT 20;
SELECT origem, inscricao_id_origem, COUNT(*) AS n
FROM core.fato_inscricao
GROUP BY origem, inscricao_id_origem HAVING COUNT(*) > 1 LIMIT 20;

-- T03: órfãos mantidos, FK nula e ID de origem presente.
SELECT origem, COUNT(*) AS inscricoes_sem_pedido,
       COUNT(*) FILTER (WHERE pedido_key IS NULL) AS fk_nula,
       COUNT(*) FILTER (WHERE pedido_id_origem IS NULL) AS id_origem_nulo
FROM core.fato_inscricao
WHERE flag_pedido_nao_encontrado
GROUP BY origem;

-- T04/T07: quatro cabeçalhos conhecidos, sem join a itens.
SELECT pedido_id_origem, valor_bruto_pedido, desconto_pedido_origem,
       valor_liquido_pedido, valor_total_cobrado, taxa_adicional_operacional
FROM core.fato_pedido
WHERE origem='magento'
  AND pedido_id_origem IN (166688,1673612,1673646,1673884)
ORDER BY pedido_id_origem;
-- Esperado: líquido 59;159.84;125.0128;119.92 e residual 14.21;19.98;26;14.99.

-- T05/T06/T18: agregar inscrições separadamente, nunca somar header após join.
SELECT i.pedido_id_origem, COUNT(*) AS bundles,
       SUM(i.valor_bruto_inscricao) AS bruto_pais,
       SUM(i.desconto_filhos_magento) AS desconto_filhos,
       SUM(i.valor_liquido_itens) AS liquido_itens,
       COUNT(*) FILTER (WHERE i.flag_excecao_financeira) AS excecoes,
       COUNT(*) FILTER (WHERE i.valor_liquido_inscricao IS NULL) AS liquidos_indeterminados
FROM core.fato_inscricao i
WHERE i.origem='magento' AND i.pedido_id_origem IN (166688,1673612,1673646,1673884)
GROUP BY i.pedido_id_origem ORDER BY i.pedido_id_origem;
-- 1673612: 2 bundles, líquido itens 159.84. 1673646: desconto header
-- não atribuído, líquido final individual NULL; 166688: bruto pais 59.

-- T08/T09: cancelados jamais contam; status 1/local 2 precisa motivo legado.
SELECT COUNT(*) AS violacoes_cancelamento_ativo
FROM core.fato_inscricao i JOIN core.fato_pedido p ON p.pedido_key=i.pedido_key
WHERE i.origem='ativo' AND i.contabiliza_inscricao IS TRUE
  AND (p.status_pedido_codigo=5 OR i.status_individual_codigo IN (5,6,7,8));
SELECT COUNT(*) AS balcao_legado_contabilizado
FROM core.fato_inscricao i JOIN core.fato_pedido p ON p.pedido_key=i.pedido_key
WHERE i.origem='ativo' AND p.status_pedido_codigo=1
  AND p.local_inscricao_codigo=2 AND i.status_individual_codigo=0
  AND i.contabiliza_inscricao IS TRUE;

-- T10/T11/T17: bruto, pago confirmado e presumido são populações distintas;
-- evento teste 22054 permanece na CORE e não entra no bruto.
SELECT origem,
       COUNT(*) FILTER (WHERE contabiliza_bruto IS TRUE) AS bruto_elegivel,
       COUNT(*) FILTER (WHERE pagamento_confirmado IS TRUE) AS confirmado,
       COUNT(*) FILTER (WHERE pagamento_presumido IS TRUE) AS presumido,
       COUNT(*) FILTER (WHERE pago_considerado IS TRUE) AS pago_considerado,
       COUNT(*) FILTER (WHERE flag_evento_teste IS TRUE
                         AND contabiliza_bruto IS TRUE) AS teste_no_bruto
FROM core.fato_inscricao GROUP BY origem;
SELECT COUNT(*) AS ativo_22054,
       COUNT(*) FILTER (WHERE flag_evento_teste) AS marcado_teste
FROM core.dim_evento WHERE seed_origem='ativo' AND seed_evento_id=22054;

-- T12: não existe união automática por SKU; vínculos manuais exigem auditoria.
SELECT criterio_vinculo, COUNT(*) AS mapas,
       COUNT(*) FILTER (WHERE criterio_vinculo='MANUAL_VALIDADO'
                         AND (revisado_por IS NULL OR revisado_em IS NULL)) AS manuais_sem_revisao
FROM core.evento_source_map GROUP BY criterio_vinculo;

-- T13: nenhum CPF em claro, token válido único (constraint); não validar
-- igualdade de pessoa pelo papel errado. Esta consulta retorna só agregados.
SELECT criterio_identificacao, cpf_valido, COUNT(*) AS pessoas
FROM core.dim_pessoa GROUP BY criterio_identificacao,cpf_valido;
SELECT origem,tipo_identificador,papel_verificado,COUNT(*) AS mapas
FROM core.pessoa_source_map GROUP BY origem,tipo_identificador,papel_verificado;

-- T15: o ID Magento deve permanecer como texto de identificador; nome sem
-- fonte comprovada permanece NULL. Zero uso de ILIKE sobre o ID numérico.
SELECT COUNT(*) AS inscricoes_magento,
       COUNT(*) FILTER (WHERE categoria_id_origem IS NOT NULL) AS ids_preservados,
       COUNT(*) FILTER (WHERE categoria_nome_origem IS NOT NULL) AS nomes_preenchidos
FROM core.fato_inscricao WHERE origem='magento';

-- T14/T20: fotografar estes totais antes/depois de dois UPSERTs idênticos e
-- após alterar controladamente um status antigo na homologação. Não fazer
-- UPDATE de teste em produção. A contagem/soma não devem mudar sem fonte nova.
SELECT origem, COUNT(*) AS pedidos,
       SUM(valor_bruto_pedido) AS bruto_pedidos,
       SUM(valor_liquido_pedido) AS liquido_pedidos
FROM core.fato_pedido GROUP BY origem;
SELECT origem, COUNT(*) AS inscricoes,
       SUM(valor_bruto_inscricao) AS bruto_inscricoes,
       SUM(valor_liquido_inscricao) AS liquido_inscricoes,
       COUNT(*) FILTER (WHERE flag_pedido_nao_encontrado) AS orfas,
       COUNT(*) FILTER (WHERE flag_evento_nao_mapeado) AS sem_evento
FROM core.fato_inscricao GROUP BY origem;

-- T16: primeiro EXPLAIN (sem ANALYZE) os SELECTs de 004 com intervalo
-- pequeno de pedido_id; verificar índice no filtro e pré-agregações. A
-- consulta ampla Magento-cliente da Fase A falhou por memória compartilhada.

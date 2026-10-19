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
       COUNT(*) FILTER (WHERE flag_pedido_nao_encontrado) AS orfas,
       COUNT(*) FILTER (WHERE flag_evento_nao_mapeado) AS sem_evento,
       COUNT(*) FILTER (WHERE estado_derivacao='PENDENTE') AS derivacao_pendente
FROM core.fato_inscricao GROUP BY origem;
SELECT origem, COUNT(*) AS inscricoes_validadas,
       SUM(valor_liquido_inscricao) AS liquido_validado
FROM core.fato_inscricao_indicadores_validos GROUP BY origem;

-- B01: o UPSERT básico não apaga classificação/financeiro, mas marca PENDENTE
-- quando a base muda. O gate da view continua fechado para TODAS as linhas.
SELECT COUNT(*) AS validado_com_hash_antigo
FROM core.fato_inscricao
WHERE estado_derivacao='VALIDADO'
  AND derivado_de_hash IS DISTINCT FROM conteudo_hash;
-- Em homologação, fotografar um lote com derivados validados, alterar uma
-- fonte básica controlada e repetir 005. Os valores financeiros/classificação
-- devem permanecer iguais na tabela, a linha deve ficar PENDENTE e sumir da
-- view válida. Restaurar a fonte e reconciliar; não fazer UPDATE em produção.
SELECT origem,
       COUNT(*) FILTER (WHERE estado_derivacao='PENDENTE'
                         AND (valor_liquido_inscricao IS NOT NULL
                              OR classificacao_venda IS NOT NULL))
           AS derivados_preservados_pendentes,
       COUNT(*) FILTER (WHERE estado_derivacao='VALIDADO'
                         AND derivado_de_hash=conteudo_hash)
           AS derivados_validos
FROM core.fato_inscricao
WHERE pedido_id_origem BETWEEN core.batch_min() AND core.batch_max()
GROUP BY origem;

-- B02: matriz Magento fechada. Zero linhas = todos os casos esperados.
WITH casos(estado,status,esperado,pago,alerta) AS (VALUES
    ('processing','approved','CONFIRMADO',TRUE,NULL::TEXT),
    ('complete','complete','CONFIRMADO',TRUE,NULL),
    ('new','new','NOVO',FALSE,NULL),
    ('pending','pending','PENDENTE',FALSE,NULL),
    ('new','pending','PENDENTE',FALSE,NULL),
    ('new','approved','INDETERMINADO',NULL::BOOLEAN,'STATUS_CONTRADITORIO'),
    ('processing','new','INDETERMINADO',NULL,'STATUS_CONTRADITORIO'),
    ('processing','canceled','CANCELADO',FALSE,'STATUS_CONTRADITORIO'),
    ('canceled','approved','CANCELADO',FALSE,'STATUS_CONTRADITORIO'),
    ('canceled','pending','CANCELADO',FALSE,'STATUS_CONTRADITORIO'),
    ('closed','complete','INDETERMINADO',NULL,'STATUS_ESPECIAL'),
    (NULL,'approved','INDETERMINADO',NULL,'STATUS_ESPECIAL')
)
SELECT estado,status,esperado,pago,alerta
FROM casos
WHERE core.magento_status_corporativo(estado,status) IS DISTINCT FROM esperado
   OR core.magento_pagamento_confirmado(estado,status) IS DISTINCT FROM pago
   OR core.magento_status_alerta(estado,status) IS DISTINCT FROM alerta;

-- B03: precedência de classificação. Cupom Ativo Grupos vence valor zero e
-- Cortesia. Cabeçalho de cupom ausente não autoriza Site/Cortesia por exclusão.
WITH casos(tipo_cupom,categoria,codigo,preco,tem_ref,tem_header,esperado) AS (VALUES
    ('Grupos','Cortesia','XX',0::NUMERIC,TRUE,TRUE,'Grupos'),
    ('Parceiros','Grupo de corrida','XX',10::NUMERIC,TRUE,TRUE,'Grupos'),
    ('Cortesia Faturada',NULL,'XX',10::NUMERIC,TRUE,TRUE,'Site'),
    (' GrUpOs  ',NULL,'XX',10::NUMERIC,TRUE,TRUE,'Grupos'),
    ('Supergrupos',NULL,'XX',10::NUMERIC,TRUE,TRUE,'Site'),
    ('Não Grupos',NULL,'XX',10::NUMERIC,TRUE,TRUE,'Site'),
    ('Grupos VIP',NULL,'XX',10::NUMERIC,TRUE,TRUE,'Site'),
    (NULL,'Cortesia','XX',0::NUMERIC,TRUE,FALSE,NULL::TEXT),
    (NULL,'Cortesia','GR123',0::NUMERIC,TRUE,FALSE,'Grupos'),
    (NULL,NULL,NULL,0::NUMERIC,FALSE,FALSE,'Cortesia'),
    (NULL,NULL,NULL,10::NUMERIC,FALSE,FALSE,'Site')
)
SELECT * FROM casos
WHERE core.classificacao_ativo(tipo_cupom,categoria,codigo,preco,
                               tem_ref,tem_header) IS DISTINCT FROM esperado;
WITH casos(grupo,cortesia,cupom,bruto,esperado) AS (VALUES
    (TRUE,TRUE,'XX',0::NUMERIC,'Grupos'),
    (FALSE,TRUE,'XX',10::NUMERIC,'Cortesia'),
    (FALSE,FALSE,'GR123',0::NUMERIC,'Grupos'),
    (FALSE,FALSE,NULL,10::NUMERIC,'Site')
)
SELECT * FROM casos
WHERE core.classificacao_magento(grupo,cortesia,cupom,bruto)
      IS DISTINCT FROM esperado;

-- B04: proteção estrutural de PII; saída somente com nomes/tipos de colunas.
SELECT table_name,column_name,data_type
FROM information_schema.columns
WHERE table_schema='core'
  AND ((table_name='core_alerta_qualidade'
        AND column_name IN ('identificador_origem','mensagem'))
       OR (table_name='core_etl_execucao'
           AND column_name IN ('erro_codigo','erro_resumido'))
       OR (table_name='dim_pessoa' AND column_name='cpf_token_seguro'))
ORDER BY table_name,column_name;
-- Esperado: identificador_origem=bigint; mensagem/erro_resumido ausentes;
-- erro_codigo=text; cpf_token_seguro=bytea. Não ler valores pessoais.

-- B05: cobertura de alertas Magento contraditórios, apenas agregados.
SELECT codigo_regra, COUNT(*) AS alertas_ativos
FROM core.core_alerta_qualidade
WHERE origem='magento' AND entidade='pedido' AND ativo
  AND codigo_regra IN ('STATUS_CONTRADITORIO','STATUS_ESPECIAL')
GROUP BY codigo_regra;

-- B06: limites pgAdmin/executor da mesma sessão; falhar se não definidos.
SELECT core.batch_min() AS id_min, core.batch_max() AS id_max;
-- Testar separadamente: [1,100000] aceita; [1,100001] rejeita.

-- B07: gate de derivados fechado nesta versão. Esperado: zero, inclusive se
-- algum registro da tabela base estiver VALIDADO. Não ler dados pessoais.
SELECT COUNT(*) AS indicadores_publicados
FROM core.fato_inscricao_indicadores_validos;

-- B08: casos de invalidação para homologação FUTURA, após reconciliador e
-- derivador aprovados. Em cada cenário, alterar uma linha de teste, reconciliar
-- atomicamente e verificar que a inscrição sai da view antes de qualquer
-- recálculo. Depois restaurar a linha e repetir; nunca testar em produção.
-- Magento: state/status; qty cancelada/reembolsada; desconto do filho, pai e
-- cabeçalho; cupom e etiqueta/regra. Ativo: classificação/código de cupom,
-- categoria e valor do kit, status detalhado. Ambas: cadastro de evento,
-- mapeamento, combo e versão de regras. Incluir INSERT/DELETE de filho/regra,
-- falha de fonte, lote repetido e virada do dia em America/Sao_Paulo.
-- Critério: nenhuma alteração acima deixa indicador obsoleto publicado.

-- T16: primeiro EXPLAIN (sem ANALYZE) os SELECTs de 004 com intervalo
-- pequeno de pedido_id; verificar índice no filtro e pré-agregações. A
-- consulta ampla Magento-cliente da Fase A falhou por memória compartilhada.

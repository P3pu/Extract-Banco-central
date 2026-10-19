-- Fase A: diagnostico CORE. Execute as consultas individualmente no pgAdmin.
-- Apenas SELECT e EXPLAIN sem ANALYZE; nenhuma instrucao grava no banco.
-- Consultas sobre grandes views podem levar dezenas de segundos. Nao execute
-- concorrente com as cargas; interrompa se o servidor sinalizar falta de recursos.
-- Nao exporte nem publique valores de documentos pessoais.

-- Q01. Objetos reais e contagem de colunas das 31 views.
SELECT t.table_schema, t.table_name, t.table_type,
       (SELECT COUNT(*) FROM information_schema.columns c
        WHERE c.table_schema = t.table_schema AND c.table_name = t.table_name) AS colunas
FROM information_schema.tables t
WHERE t.table_schema IN ('raw', 'staging', 'core')
ORDER BY t.table_schema, t.table_name;

-- Q02. Tipos, nulabilidade e posicao das colunas STAGING (comparar com Excel).
SELECT table_name, ordinal_position, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'staging'
ORDER BY table_name, ordinal_position;

-- Q03. Chaves primarias RAW, inclusive identidades distintas por origem.
SELECT tc.table_name,
       string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS pk
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON kcu.constraint_schema = tc.constraint_schema
 AND kcu.constraint_name = tc.constraint_name
WHERE tc.table_schema = 'raw' AND tc.constraint_type = 'PRIMARY KEY'
GROUP BY tc.table_name ORDER BY tc.table_name;

-- Q04. Definicoes implantadas das views criticas. Saida e SQL, nao dados.
SELECT c.relname AS view_name, pg_get_viewdef(c.oid, true) AS definicao
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'staging'
  AND c.relname IN ('ativo_inscricao', 'ativo_pagamento', 'ativo_cupom',
                    'magento_inscricao', 'magento_pedido_regra',
                    'magento_bundle_componente')
ORDER BY c.relname;

-- Q05. Dependencias ausentes para cupom e status detalhado.
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema IN ('raw', 'staging')
  AND (table_name LIKE '%cupom%' OR table_name LIKE '%status%')
ORDER BY table_schema, table_name;

-- Q06. Cardinalidade e orfaos Ativo. Os IDs continuam na view.
SELECT COUNT(*) AS inscricoes,
       COUNT(*) FILTER (WHERE NOT pedido_mapeado) AS sem_pedido,
       COUNT(*) FILTER (WHERE NOT evento_mapeado) AS sem_evento,
       COUNT(*) FILTER (WHERE NOT modalidade_mapeada) AS sem_modalidade,
       COUNT(*) FILTER (WHERE NOT categoria_mapeada) AS sem_categoria,
       COUNT(*) FILTER (WHERE NOT tamanho_camiseta_mapeado) AS sem_tamanho
FROM staging.ativo_inscricao;

-- Q07. Cardinalidade e ambiguidade Magento.
SELECT COUNT(*) AS inscricoes,
       COUNT(*) FILTER (WHERE evento_nao_mapeado) AS sem_evento,
       COUNT(*) FILTER (WHERE cliente_ambiguo) AS cliente_ambiguo,
       COUNT(*) FILTER (WHERE modalidade_ambigua) AS modalidade_ambigua
FROM staging.magento_inscricao;

-- Q08. Comparar grão de inscricao com as fontes principais.
SELECT 'ativo_inscricao' AS entidade,
       (SELECT COUNT(*) FROM raw.ativo_pedido_evento) AS linhas_raw,
       (SELECT COUNT(*) FROM staging.ativo_inscricao) AS linhas_staging
UNION ALL
SELECT 'magento_bundle_pai',
       (SELECT COUNT(*) FROM raw.magento_sales_order_item
        WHERE product_type = 'bundle' AND parent_item_id IS NULL),
       (SELECT COUNT(*) FROM staging.magento_inscricao);

-- Q09. Status individual realmente usados nas inscricoes Ativo.
SELECT id_status_detalhado, COUNT(*) AS inscricoes
FROM raw.ativo_pedido_evento
GROUP BY id_status_detalhado ORDER BY id_status_detalhado;

-- Q10. Pares estado/status Magento, incluindo conflitos com cancelamento.
SELECT state, status, COUNT(*) AS pedidos
FROM raw.magento_sales_order
GROUP BY state, status ORDER BY pedidos DESC;

-- Q11. Pedidos financeiros conhecidos, sem informacao de cliente.
SELECT pedido_id, subtotal, desconto, subtotal + desconto AS liquido_cabecalho,
       frete, imposto, valor_total,
       valor_total - (subtotal + desconto) AS residual_operacional
FROM staging.magento_pedido
WHERE pedido_id IN (166688, 1673612, 1673646, 1673884)
ORDER BY pedido_id;

-- Q12. Agregacao separada de pais/filhos: nao multiplica o cabecalho.
WITH pais AS (
    SELECT pedido_id, item_id, valor_linha, desconto, quantidade_pedida,
           quantidade_cancelada, quantidade_reembolsada
    FROM staging.magento_item_pedido
    WHERE pedido_id IN (166688, 1673612, 1673646, 1673884)
      AND eh_bundle AND item_pai_id IS NULL
), filhos AS (
    SELECT i.item_pai_id, COUNT(*) AS qtd_filhos,
           SUM(i.valor_linha) AS bruto_filhos,
           SUM(i.desconto) AS desconto_filhos
    FROM staging.magento_item_pedido i
    JOIN pais p ON p.item_id = i.item_pai_id
    GROUP BY i.item_pai_id
)
SELECT p.pedido_id, COUNT(*) AS bundles,
       SUM(p.valor_linha) AS bruto_pais,
       SUM(p.desconto) AS desconto_pais,
       SUM(COALESCE(f.qtd_filhos, 0)) AS filhos,
       SUM(f.bruto_filhos) AS bruto_filhos,
       SUM(f.desconto_filhos) AS desconto_filhos,
       COUNT(*) FILTER (WHERE p.quantidade_pedida IS DISTINCT FROM 1) AS qtd_nao_um,
       COUNT(*) FILTER (WHERE COALESCE(p.quantidade_cancelada, 0) > 0
                           OR COALESCE(p.quantidade_reembolsada, 0) > 0) AS parcial
FROM pais p LEFT JOIN filhos f ON f.item_pai_id = p.item_id
GROUP BY p.pedido_id ORDER BY p.pedido_id;

-- Q13. Excecoes estruturais em todos os bundles pais. Pode varrer ~7 mi itens.
SELECT COUNT(*) AS bundles_pai,
       COUNT(*) FILTER (WHERE qty_ordered IS DISTINCT FROM 1) AS qtd_nao_um,
       COUNT(*) FILTER (WHERE COALESCE(qty_canceled, 0) > 0) AS com_cancelamento,
       COUNT(*) FILTER (WHERE COALESCE(qty_refunded, 0) > 0) AS com_reembolso
FROM raw.magento_sales_order_item
WHERE product_type = 'bundle' AND parent_item_id IS NULL;

-- Q14. Cobertura dos IDs Ativo, sem devolver identificadores individuais.
SELECT COUNT(*) AS inscricoes,
       COUNT(*) FILTER (WHERE id_usuario IS NOT NULL) AS com_usuario,
       COUNT(*) FILTER (WHERE id_usuario_balcao IS NOT NULL) AS com_balcao,
       COUNT(*) FILTER (WHERE id_usuario IS NOT NULL
                           AND id_usuario_balcao IS NOT NULL) AS com_ambos
FROM raw.ativo_pedido_evento;

-- Q15. Cobertura de documentos nos cadastros. Nao avalia papel ou validade.
SELECT 'ativo_usuario' AS fonte, COUNT(*) AS pessoas,
       COUNT(*) FILTER (WHERE NULLIF(btrim(nr_documento), '') IS NOT NULL) AS com_documento
FROM raw.ativo_usuario
UNION ALL
SELECT 'ativo_usuario_balcao', COUNT(*),
       COUNT(*) FILTER (WHERE NULLIF(btrim(nr_documento), '') IS NOT NULL)
FROM raw.ativo_usuario_balcao
UNION ALL
SELECT 'magento_cliente', COUNT(*),
       COUNT(*) FILTER (WHERE NULLIF(btrim(taxvat), '') IS NOT NULL)
FROM raw.magento_customer;

-- Q16. CPF: amostra de 50 mil IDs recentes por cadastro; so contagens saem.
-- O documento fica dentro do executor PostgreSQL e nao aparece no resultado.
WITH docs AS (
    SELECT 'ativo_usuario' AS fonte, nr_documento AS doc
    FROM (SELECT nr_documento FROM raw.ativo_usuario
          ORDER BY id_usuario DESC LIMIT 50000) a
    UNION ALL
    SELECT 'ativo_balcao', nr_documento
    FROM (SELECT nr_documento FROM raw.ativo_usuario_balcao
          ORDER BY id_usuario DESC LIMIT 50000) b
    UNION ALL
    SELECT 'magento_cliente', taxvat
    FROM (SELECT taxvat FROM raw.magento_customer
          ORDER BY entity_id DESC LIMIT 50000) m
), norm AS (
    SELECT fonte, regexp_replace(COALESCE(doc, ''), '[^0-9]', '', 'g') AS cpf
    FROM docs
), checked AS (
    SELECT fonte, cpf,
           CASE WHEN length(cpf) = 11 AND cpf <> repeat(left(cpf, 1), 11)
                THEN
                  (SELECT ((SUM(substr(cpf, i, 1)::integer * (11-i)) * 10) % 11) % 10
                   FROM generate_series(1, 9) g(i)) = substr(cpf, 10, 1)::integer
                  AND
                  (SELECT ((SUM(substr(cpf, i, 1)::integer * (12-i)) * 10) % 11) % 10
                   FROM generate_series(1, 10) g(i)) = substr(cpf, 11, 1)::integer
                ELSE FALSE END AS cpf_valido
    FROM norm
)
SELECT fonte, COUNT(*) AS amostra,
       COUNT(*) FILTER (WHERE cpf <> '') AS com_digitos,
       COUNT(*) FILTER (WHERE length(cpf) = 11) AS onze_digitos,
       COUNT(*) FILTER (WHERE cpf_valido) AS cpf_valido
FROM checked GROUP BY fonte ORDER BY fonte;

-- Q17. Comprador Magento, amostra recente e join pela PK do cliente.
WITH pedidos AS (
    SELECT entity_id, customer_id FROM raw.magento_sales_order
    ORDER BY entity_id DESC LIMIT 50000
)
SELECT COUNT(*) AS pedidos,
       COUNT(*) FILTER (WHERE p.customer_id IS NOT NULL) AS com_customer_id,
       COUNT(*) FILTER (WHERE c.entity_id IS NOT NULL) AS cliente_encontrado
FROM pedidos p LEFT JOIN raw.magento_customer c ON c.entity_id = p.customer_id;

-- Q18. Campo de comprador Ativo e composicao de combo: verificar ausencia RAW.
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'raw'
  AND ((table_name = 'ativo_pedido' AND column_name IN ('id_usuario', 'id_combo'))
       OR (table_name = 'ativo_combo' AND column_name IN ('nr_qntprovas', 'ds_titulo'))
       OR table_name LIKE '%combo_evento_categoria%')
ORDER BY table_name, column_name;

-- Q19. dt_pagamento nao equivale a pagamento confirmado: apenas contagens.
SELECT fl_status, COUNT(*) AS pagamentos,
       COUNT(*) FILTER (WHERE NULLIF(btrim(dt_pagamento), '') IS NOT NULL) AS com_data
FROM raw.ativo_pedido_pagamento
GROUP BY fl_status ORDER BY fl_status;

-- Q20. Cardinalidade de pagamentos em recorte recente. Amostra != historia.
WITH amostra AS (
    SELECT id_pedido FROM raw.ativo_pedido_pagamento
    ORDER BY id_pedido_pagamento DESC LIMIT 100000
), por_pedido AS (
    SELECT id_pedido, COUNT(*) AS qtd FROM amostra GROUP BY id_pedido
)
SELECT COUNT(*) AS pedidos_na_amostra,
       COUNT(*) FILTER (WHERE qtd > 1) AS com_multiplos_pagamentos,
       MAX(qtd) AS max_pagamentos
FROM por_pedido;

-- Q21. Plano de uma consulta pesada sem executa-la. Sem ANALYZE.
EXPLAIN
SELECT COUNT(*) FROM staging.ativo_inscricao WHERE NOT pedido_mapeado;

-- C2.1 / Naruto: catálogo e evento por PK. Não lê PII nem usa CORE.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';
SELECT current_database() AS banco, current_setting('transaction_read_only') AS modo,
       1 / CASE WHEN current_database() = 'Atendimento'
                     AND current_setting('transaction_read_only') = 'on'
                THEN 1 ELSE 0 END AS destino_validado;

-- Contratos ausentes: presença de coluna não prova extração completa.
WITH dependencias(esquema, relacao, coluna) AS (VALUES
    ('raw','ativo_cupom_desconto','id_cupom_desconto'),
    ('raw','ativo_cupom_desconto','en_cupom_classificacao'),
    ('staging','ativo_cupom_desconto','classificacao'),
    ('raw','ativo_status_detalhado','id_status_detalhado'),
    ('staging','ativo_status_detalhado','descricao'),
    ('raw','ativo_pedido','id_usuario'),
    ('staging','ativo_pedido','comprador_usuario_id'),
    ('raw','ativo_combo','nr_qntprovas'),
    ('raw','ativo_combo_evento_categoria','id_combo')
)
SELECT d.esquema, d.relacao, d.coluna,
       c.column_name IS NOT NULL AS coluna_disponivel,
       c.data_type, c.is_nullable
FROM dependencias d LEFT JOIN information_schema.columns c
  ON c.table_schema=d.esquema AND c.table_name=d.relacao
 AND c.column_name=d.coluna
ORDER BY d.esquema,d.relacao,d.coluna;

-- Índices em colunas de filtro: ausência exige revisão de custo adicional.
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname='raw'
  AND tablename IN ('magento_sales_order','magento_sales_order_item',
                    'ativo_pedido_evento','ativo_pedido_pagamento',
                    'ativo_cupom_desconto_item')
ORDER BY tablename,indexname;

-- Evento teste conhecido: somente ID e metadados não pessoais.
SELECT evento_id, data_evento IS NULL AS data_evento_nula,
       TRUE AS evento_teste_curado
FROM staging.ativo_evento WHERE evento_id=22054;
COMMIT;

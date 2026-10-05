-- Cada consulta de duplicidade deve retornar 0 linhas.
SELECT pedido_id, COUNT(*) FROM staging.ativo_pedido GROUP BY pedido_id HAVING COUNT(*) > 1;
SELECT evento_id, COUNT(*) FROM staging.ativo_evento GROUP BY evento_id HAVING COUNT(*) > 1;
SELECT modalidade_id, COUNT(*) FROM staging.ativo_modalidade GROUP BY modalidade_id HAVING COUNT(*) > 1;
SELECT categoria_id, COUNT(*) FROM staging.ativo_categoria GROUP BY categoria_id HAVING COUNT(*) > 1;
SELECT tamanho_camiseta_id, COUNT(*) FROM staging.ativo_tamanho_camiseta GROUP BY tamanho_camiseta_id HAVING COUNT(*) > 1;
SELECT usuario_id, COUNT(*) FROM staging.ativo_usuario GROUP BY usuario_id HAVING COUNT(*) > 1;
SELECT usuario_balcao_id, COUNT(*) FROM staging.ativo_usuario_balcao GROUP BY usuario_balcao_id HAVING COUNT(*) > 1;
SELECT forma_pagamento_id, COUNT(*) FROM staging.ativo_forma_pagamento GROUP BY forma_pagamento_id HAVING COUNT(*) > 1;
SELECT pagamento_id, COUNT(*) FROM staging.ativo_pagamento GROUP BY pagamento_id HAVING COUNT(*) > 1;
SELECT transacao_id, COUNT(*) FROM staging.ativo_transacao GROUP BY transacao_id HAVING COUNT(*) > 1;
SELECT pedido_produto_id, COUNT(*) FROM staging.ativo_pedido_produto GROUP BY pedido_produto_id HAVING COUNT(*) > 1;
SELECT endereco_id, COUNT(*) FROM staging.ativo_endereco_pedido GROUP BY endereco_id HAVING COUNT(*) > 1;
SELECT cidade_registro_id, COUNT(*) FROM staging.ativo_cidade GROUP BY cidade_registro_id HAVING COUNT(*) > 1;
SELECT estado_registro_id, COUNT(*) FROM staging.ativo_estado GROUP BY estado_registro_id HAVING COUNT(*) > 1;
SELECT pais_id, COUNT(*) FROM staging.ativo_pais GROUP BY pais_id HAVING COUNT(*) > 1;
SELECT combo_id, COUNT(*) FROM staging.ativo_combo GROUP BY combo_id HAVING COUNT(*) > 1;
SELECT cupom_id, COUNT(*) FROM staging.ativo_cupom GROUP BY cupom_id HAVING COUNT(*) > 1;
SELECT inscricao_id, COUNT(*) FROM staging.ativo_inscricao GROUP BY inscricao_id HAVING COUNT(*) > 1;

-- As seguintes views preservam toda a fonte principal, sem filtro estrutural.
SELECT 'pedido' AS entidade, (SELECT COUNT(*) FROM raw.ativo_pedido) AS raw_count,
       (SELECT COUNT(*) FROM staging.ativo_pedido) AS staging_count;
SELECT 'inscricao' AS entidade, (SELECT COUNT(*) FROM raw.ativo_pedido_evento) AS raw_count,
       (SELECT COUNT(*) FROM staging.ativo_inscricao) AS staging_count;
SELECT 'pagamento' AS entidade, (SELECT COUNT(*) FROM raw.ativo_pedido_pagamento) AS raw_count,
       (SELECT COUNT(*) FROM staging.ativo_pagamento) AS staging_count;
SELECT 'transacao' AS entidade, (SELECT COUNT(*) FROM raw.ativo_transacao) AS raw_count,
       (SELECT COUNT(*) FROM staging.ativo_transacao) AS staging_count;
SELECT 'produto_pedido' AS entidade, (SELECT COUNT(*) FROM raw.ativo_pedido_produto) AS raw_count,
       (SELECT COUNT(*) FROM staging.ativo_pedido_produto) AS staging_count;
SELECT 'endereco_pedido' AS entidade, (SELECT COUNT(*) FROM raw.ativo_pedido_endereco) AS raw_count,
       (SELECT COUNT(*) FROM staging.ativo_endereco_pedido) AS staging_count;

-- Órfãos são preservados; TESTE DEV continua consultável.
SELECT inscricao_id, evento_id, evento_mapeado, modalidade_id, modalidade_mapeada,
       categoria_id, categoria_mapeada, tamanho_camiseta_id, tamanho_camiseta_mapeado
FROM staging.ativo_inscricao WHERE evento_id = 22054 LIMIT 1;

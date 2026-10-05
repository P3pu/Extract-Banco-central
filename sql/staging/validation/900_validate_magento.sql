-- Cada consulta de duplicidade deve retornar 0 linhas.
SELECT option_id, COUNT(*) FROM staging.magento_option_label GROUP BY option_id HAVING COUNT(*) > 1;
SELECT pedido_id, COUNT(*) FROM staging.magento_pedido GROUP BY pedido_id HAVING COUNT(*) > 1;
SELECT item_id, COUNT(*) FROM staging.magento_item_pedido GROUP BY item_id HAVING COUNT(*) > 1;
SELECT produto_id, COUNT(*) FROM staging.magento_produto GROUP BY produto_id HAVING COUNT(*) > 1;
SELECT produto_id, COUNT(*) FROM staging.magento_produto_evento_mapeamento GROUP BY produto_id HAVING COUNT(*) > 1;
SELECT evento_id, COUNT(*) FROM staging.magento_evento GROUP BY evento_id HAVING COUNT(*) > 1;
SELECT cliente_id, COUNT(*) FROM staging.magento_cliente GROUP BY cliente_id HAVING COUNT(*) > 1;
SELECT endereco_id, COUNT(*) FROM staging.magento_endereco_cliente GROUP BY endereco_id HAVING COUNT(*) > 1;
SELECT item_id, COUNT(*) FROM staging.magento_item_cliente GROUP BY item_id HAVING COUNT(*) > 1;
SELECT cliente_id, COUNT(*) FROM staging.magento_cliente_empresa GROUP BY cliente_id HAVING COUNT(*) > 1;
SELECT pedido_id, regra_id, COUNT(*) FROM staging.magento_pedido_regra WHERE regra_id IS NOT NULL GROUP BY pedido_id, regra_id HAVING COUNT(*) > 1;
SELECT pedido_id, regra_id_bruto, COUNT(*) FROM staging.magento_pedido_regra WHERE regra_id IS NULL GROUP BY pedido_id, regra_id_bruto HAVING COUNT(*) > 1;
SELECT componente_item_id, COUNT(*) FROM staging.magento_bundle_componente GROUP BY componente_item_id HAVING COUNT(*) > 1;
SELECT inscricao_id, COUNT(*) FROM staging.magento_inscricao GROUP BY inscricao_id HAVING COUNT(*) > 1;

-- Views que preservam integralmente o grão: contagens RAW = STAGING.
SELECT 'pedido' AS entidade, (SELECT COUNT(*) FROM raw.magento_sales_order) AS raw_count,
       (SELECT COUNT(*) FROM staging.magento_pedido) AS staging_count;
SELECT 'item_pedido' AS entidade, (SELECT COUNT(*) FROM raw.magento_sales_order_item) AS raw_count,
       (SELECT COUNT(*) FROM staging.magento_item_pedido) AS staging_count;
SELECT 'produto' AS entidade, (SELECT COUNT(*) FROM raw.magento_product) AS raw_count,
       (SELECT COUNT(*) FROM staging.magento_produto) AS staging_count;
SELECT 'cliente' AS entidade, (SELECT COUNT(*) FROM raw.magento_customer) AS raw_count,
       (SELECT COUNT(*) FROM staging.magento_cliente) AS staging_count;
SELECT 'endereco_cliente' AS entidade, (SELECT COUNT(*) FROM raw.magento_customer_address) AS raw_count,
       (SELECT COUNT(*) FROM staging.magento_endereco_cliente) AS staging_count;
SELECT 'cliente_empresa' AS entidade, (SELECT COUNT(*) FROM raw.magento_company_user) AS raw_count,
       (SELECT COUNT(*) FROM staging.magento_cliente_empresa) AS staging_count;

-- Subconjuntos estruturais: eventos resolvidos e bundles pais, respectivamente.
SELECT (SELECT COUNT(*) FROM staging.magento_evento) AS eventos_resolvidos,
       (SELECT COUNT(*) FROM staging.magento_inscricao) AS bundles_pais,
       (SELECT COUNT(*) FROM raw.magento_sales_order_item WHERE product_type = 'bundle') AS bundles_raw;

-- Casos conhecidos: produto 47522 -> evento 48158; pai e três filhos presentes.
SELECT produto_id, evento_direto_id, evento_id, metodo_mapeamento
FROM staging.magento_produto_evento_mapeamento WHERE produto_id = 47522;
SELECT inscricao_id, qtd_componentes FROM staging.magento_inscricao WHERE inscricao_id = 703415;
SELECT componente_item_id, inscricao_item_id FROM staging.magento_bundle_componente
WHERE inscricao_item_id = 703415 ORDER BY componente_item_id;

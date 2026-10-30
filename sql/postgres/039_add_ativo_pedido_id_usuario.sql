-- Comprador do pedido Ativo (sa_pedido.id_usuario). Aplicar com a automação
-- parada: o contrato RAW passa a exigir a coluna. Nasce nulo; o preenchimento
-- histórico é feito por `python -m src.pipeline.ativo_pedido_usuario`, que só
-- então aplica NOT NULL.
ALTER TABLE raw.ativo_pedido ADD COLUMN IF NOT EXISTS id_usuario INTEGER;

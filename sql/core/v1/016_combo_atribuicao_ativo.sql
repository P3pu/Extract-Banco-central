-- Combos vendidos no Ativo, migrados ou não ao Magento (decisão 03/11/2026:
-- o Ativo é a informação original; migração é só sinalização na view).
-- O Ativo traz uma inscrição por prova e um único combo por pedido
-- (sa_pedido.id_combo). Pertencem ao combo todas as inscrições do pedido, menos
-- os produtos (core.evento_produto). O cardápio não define o combo: está
-- incompleto para etapas trocadas depois da venda (ensaio de 03/11/2026).
-- Um pedido pode ter vários combos vendidos: um por participante e, quando as
-- inscrições do participante são múltiplo exato do tamanho do combo, um por
-- múltiplo. Tamanho = quantidade mais comum de inscrições daquele combo_id;
-- menor que 2 não é confiável e não separa combos.
WITH escopo AS (
    SELECT f.inscricao_key, f.pedido_id_origem, f.evento_id_origem,
           COALESCE(f.participante_namespace_origem || f.participante_id_origem::text,
                    'sem_participante') participante,
           c.combo_key, c.combo_id_origem
    FROM core.fato_inscricao f
    JOIN core.dim_combo c ON c.combo_key=f.combo_key AND c.origem='ativo'
    WHERE f.origem='ativo'
      AND (%(todos)s OR f.pedido_id_origem=ANY(%(ativo_pedidos)s::bigint[]))
), vendas AS (
    SELECT f.combo_key, f.pedido_id_origem,
           COALESCE(f.participante_namespace_origem || f.participante_id_origem::text,
                    'sem_participante') participante,
           count(*) qtd
    FROM core.fato_inscricao f
    JOIN core.dim_combo c ON c.combo_key=f.combo_key AND c.origem='ativo'
    WHERE f.origem='ativo'
      AND f.combo_key IN (SELECT combo_key FROM escopo)
      AND NOT EXISTS (SELECT 1 FROM core.evento_produto x
                      WHERE x.evento_id_origem=f.evento_id_origem)
    GROUP BY 1,2,3
), tamanho AS (
    SELECT combo_key, mode() WITHIN GROUP (ORDER BY qtd) tamanho
    FROM vendas GROUP BY 1
), casadas AS (
    SELECT e.*,
           row_number() OVER w ordem,
           count(*) OVER (PARTITION BY e.pedido_id_origem, e.participante, e.combo_key) qtd
    FROM escopo e
    WHERE NOT EXISTS (SELECT 1 FROM core.evento_produto x
                      WHERE x.evento_id_origem=e.evento_id_origem)
    WINDOW w AS (PARTITION BY e.pedido_id_origem, e.participante, e.combo_key
                 ORDER BY e.inscricao_key)
), desejadas AS (
    SELECT c.inscricao_key, c.combo_key,
           c.pedido_id_origem::text || ':ativo:' || c.combo_id_origem || ':' || c.participante
             || CASE WHEN t.tamanho>=2 AND c.qtd>t.tamanho AND c.qtd %% t.tamanho=0
                          AND c.ordem>t.tamanho
                     THEN ':' || ((c.ordem-1)/t.tamanho+1)::text ELSE '' END grupo_comercial_id
    FROM casadas c JOIN tamanho t ON t.combo_key=c.combo_key
), removidas AS (
    DELETE FROM core.combo_inscricao_atribuicao t
    USING escopo e
    WHERE t.inscricao_key=e.inscricao_key
      -- Inclui as atribuições da antiga regra por SKU ("<pedido>:<SKU>COMBO<n>").
      AND (t.grupo_comercial_id LIKE '%%:ativo:%%'
           OR t.grupo_comercial_id LIKE '%%:%%COMBO%%')
      AND NOT EXISTS (SELECT 1 FROM desejadas d WHERE d.inscricao_key=t.inscricao_key)
    RETURNING 1
)
INSERT INTO core.combo_inscricao_atribuicao
    (inscricao_key, combo_key, grupo_comercial_id, validado_por, validado_em)
SELECT inscricao_key, combo_key, grupo_comercial_id,
       %(validado_por)s, %(validado_em)s::timestamptz
FROM desejadas
ON CONFLICT (inscricao_key) DO UPDATE SET
    combo_key=EXCLUDED.combo_key,
    grupo_comercial_id=EXCLUDED.grupo_comercial_id,
    validado_por=EXCLUDED.validado_por,
    validado_em=EXCLUDED.validado_em
WHERE (core.combo_inscricao_atribuicao.combo_key,
       core.combo_inscricao_atribuicao.grupo_comercial_id)
      IS DISTINCT FROM (EXCLUDED.combo_key, EXCLUDED.grupo_comercial_id);

-- Magento + Ativo em uma lista: somente fatos e dim_pessoa da CORE.
-- Executar no Atendimento apos a migracao 008 e backfill da dimensao.
-- Datas de pedido sao timestamps sem fuso; comparar como dia de Sao Paulo
-- pressupoe que a origem foi carregada nesse mesmo fuso (validar na fonte).
-- A CORE ainda nao identifica o comprador Ativo; nao inferir do participante.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15min';
SET LOCAL lock_timeout = '3s';

SELECT current_database() AS banco,
       current_setting('transaction_read_only') AS somente_leitura;

WITH inscricoes_pagas AS (
    SELECT f.origem, f.pedido_key, f.participante_key,
           p.comprador_key, p.data_pedido::date AS data_movimento
    FROM core.fato_inscricao f
    JOIN core.fato_pedido p ON p.pedido_key = f.pedido_key
    WHERE f.origem IN ('magento','ativo')
      AND f.origem = p.origem
      AND p.data_pedido::date >=
          (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date
      AND p.pagamento_confirmado IS TRUE
      AND f.pagamento_confirmado IS TRUE
      AND f.contabiliza_inscricao IS TRUE
      AND f.flag_cancelado_inscricao IS FALSE
      AND f.flag_evento_teste IS FALSE
      AND (f.origem <> 'magento' OR
           (f.quantidade_pedida = 1
            AND COALESCE(f.quantidade_cancelada,0) = 0
            AND COALESCE(f.quantidade_reembolsada,0) = 0))
      AND (f.origem <> 'ativo' OR
           (f.classificacao_comercial = 'SITE'
            AND f.classificacao_incompleta IS FALSE
            AND f.combo_key IS NULL))
), pessoas AS (
    SELECT DISTINCT comprador_key AS pessoa_key, data_movimento
    FROM inscricoes_pagas
    WHERE origem='magento' AND comprador_key IS NOT NULL
    UNION ALL
    SELECT participante_key, data_movimento
    FROM inscricoes_pagas
    WHERE participante_key IS NOT NULL
), identificadas AS (
    SELECT p.data_movimento, d.pessoa_key, d.cpf, d.nome, d.email,
           d.pessoa_key AS chave_pessoa
    FROM pessoas p
    JOIN core.dim_pessoa d ON d.pessoa_key=p.pessoa_key
)
SELECT (ARRAY_AGG(nome ORDER BY data_movimento DESC)
        FILTER (WHERE nome IS NOT NULL))[1] AS "Nome",
       (ARRAY_AGG(email ORDER BY data_movimento DESC)
        FILTER (WHERE email IS NOT NULL))[1] AS "E-mail",
       COALESCE((ARRAY_AGG(cpf ORDER BY data_movimento DESC)
                 FILTER (WHERE cpf IS NOT NULL))[1], '') AS "CPF"
FROM identificadas
GROUP BY chave_pessoa
ORDER BY "Nome" NULLS LAST, "CPF";

COMMIT;

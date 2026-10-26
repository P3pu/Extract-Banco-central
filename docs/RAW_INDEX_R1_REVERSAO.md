# RAW R1 — plano de reversão separado (não autorizado)

Nenhum `DROP INDEX` é executado pelos scripts R1. Reversão no Naruto exige
decisão e autorização próprias, mesmo se a criação concorrente falhar.

1. Suspender novas tentativas de migração e registrar erro, horário, estado
   das cargas e progresso. Verificar por consulta read-only o OID, a definição,
   `indisvalid`, `indisready`, `indislive`, tamanho e dependências do índice.
   Confirmar que o alvo é **somente** `raw.idx_magento_sales_order_item_order_id`
   no banco `Atendimento`; não inferir pelo nome sem catálogo.
2. Se válido mas houver regressão, comparar métricas de carga e planos antes
   de optar por remoção. Se inválido, investigar a causa e possíveis efeitos
   de manutenção; não assumir que `IF NOT EXISTS` reparará o estado.
3. Somente após aprovação específica, o DBA pode escolher reconstrução
   concorrente ou remoção manual do índice exato, em sessão autocommit fora de
   `BEGIN`, com janela e monitoramento próprios. Nunca remover um índice
   existente de definição desconhecida nem usar remoção em lote. Reconstruir
   pode não resolver falta de espaço ou carga excessiva.
4. Confirmar pelo catálogo a ausência ou validade resultante, revisar plano
   com `EXPLAIN` sem `ANALYZE` e monitorar cargas. Registrar a decisão e
   evidências. Não reexecutar migração automaticamente após falha.

Referências oficiais: [CREATE INDEX](https://www.postgresql.org/docs/16/sql-createindex.html)
e [REINDEX](https://www.postgresql.org/docs/16/sql-reindex.html).

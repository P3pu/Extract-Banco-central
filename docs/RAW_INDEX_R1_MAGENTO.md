# RAW R1 — proposta de índice Magento (revisão, sem implantação)

## Escopo e decisão

Adicionar uma única vez um índice B-tree simples em
`raw.magento_sales_order_item(order_id)`, fora da carga RAW e do pipeline
Python. Na C2, a busca por quatro pedidos teve `Parallel Seq Scan` e custo
estimado de cerca de 386 mil. Isso motiva a proposta, mas não garante que o
planejador use o índice em todas as consultas. A migração está em
`sql/postgres/migrations/001_idx_magento_item_order_id.sql`; **não** está no
carregamento automático.

Esta entrega somente prepara arquivos. Nenhum SQL foi executado no Naruto ou
no Docker. A CORE não é criada, a `main` não é alterada e a view de indicadores
continua fechada.

## Dimensionamento antes de autorizar

O tamanho real da tabela e o espaço livre **ainda são indeterminados**: não
houve consulta ao Naruto nesta fase. Após aprovação separada para diagnóstico,
usar `001_idx_magento_item_order_id_diagnostics_readonly.sql` para obter
`reltuples`, `pg_table_size`, `pg_indexes_size`, `pg_total_relation_size` e
estatísticas de inserção/atualização. A faixa de 24–64 bytes por linha
mostrada ali é apenas heurística de planejamento, não previsão física; dados,
deduplicação, páginas, bloat e operações concorrentes mudam o resultado.
Registrar também crescimento recente e eventual defasagem de estatísticas.

Um administrador do Naruto deve identificar o filesystem que armazena o
`PGDATA`/tablespace da tabela e conferir espaço livre e alertas da plataforma
(por exemplo, `df -h` no filesystem correto). A consulta SQL não mede espaço
livre no disco. Reservar folga para o índice, WAL, arquivos temporários e
continuidade das cargas; não prosseguir se a margem não for suficiente. O
limiar operacional deve ser aprovado pelo responsável pela infraestrutura.

## Riscos e monitoramento

`CREATE INDEX CONCURRENTLY` não pode rodar dentro de transação explícita.
Ele faz duas varreduras da tabela e aguarda transações relevantes; permite
escritas concorrentes, mas consome I/O, CPU, WAL e espaço. Inserções e
atualizações futuras passarão a manter mais um índice, podendo elevar a
latência das cargas incrementais. Agendar janela de baixa atividade e medir
tempos/erros de carga antes e depois. Evitar outra criação concorrente de
índice na mesma tabela. Usar o monitoramento de locks/atividade e
`pg_stat_progress_create_index` (consulta read-only preparada).

O `IF NOT EXISTS` só evita conflito de nome; **não** comprova definição
correta nem integridade. `preflight` e `verify` examinam catálogo, B-tree,
coluna, ordem, opclass, ausência de predicado/expressão e os estados
`indisvalid`, `indisready` e `indislive`. Um índice inválido, de definição
divergente ou outro B-tree começando por `order_id` faz o preflight falhar.
Falhas de criação concorrente podem deixar um índice inválido, que não deve
ser considerado implantação bem-sucedida e pode continuar gerando custo de
manutenção. Não há remoção automática; investigar antes de qualquer reparo.

Referências oficiais: [CREATE INDEX](https://www.postgresql.org/docs/16/sql-createindex.html),
[progresso de operações](https://www.postgresql.org/docs/16/progress-reporting.html),
[estatísticas](https://www.postgresql.org/docs/16/monitoring-stats.html),
[funções de tamanho](https://www.postgresql.org/docs/16/functions-admin.html).

## Sequência proposta — requer autorizações futuras

1. Aprovar e concluir o laboratório R1 **em volume novo**; registrar os
   resultados de `schema`, `seed`, `index`, `test` e `existing`.
2. Autorizar separadamente diagnóstico read-only no Naruto. Verificar host,
   porta, banco `Atendimento`, janela, estimativas, espaço livre, locks e carga
   atual. Executar o diagnóstico com `psql -X -v ON_ERROR_STOP=1`, sem senha
   em linha de comando e sem exportar dados pessoais.
3. Revisar o plano operacional e obter autorização específica de produção.
   Conectar ao destino confirmado, executar `preflight` com
   `psql -X -v ON_ERROR_STOP=1 -f ...`; só prosseguir se retornar `A_CRIAR`
   (ou `JA_VALIDO` com definição validada). Não executar arquivo SQL em
   executor que imponha `BEGIN` ou `--single-transaction`.
4. Em sessão autocommit isolada, executar apenas o arquivo de migração. O
   operador deve acompanhar tempo, locks, `pg_stat_progress_create_index`,
   espaço e saúde das cargas. Interromper e reavaliar se a janela/limites
   aprovados forem excedidos; não contornar guardas.
5. Executar `verify` e então o `explain_readonly` (sem `ANALYZE`) para os quatro
   pedidos. Comparar custo e forma do plano com a linha de base C2, sabendo
   que estatísticas e parâmetros também influenciam a escolha. Observar
   métricas de carga incremental após a mudança.

Os scripts read-only destinados ao Naruto são os arquivos
`*_diagnostics_readonly.sql` e `*_explain_readonly.sql`; ambos validam banco
`Atendimento`, usam `BEGIN READ ONLY`, `statement_timeout='5s'` e
`lock_timeout='500ms'`. O operador ainda deve confirmar host/porta fora do
SQL. `preflight` e `verify` também são read-only, mas genéricos para Docker e
produção; sua execução em qualquer ambiente depende de autorização.

## Critérios de aceite e cancelamento

Autorizar somente se: laboratório isolado aprovado; contrato RAW e
estatísticas conferidos; espaço livre e folga operacional aprovados; índice
ausente ou exato/válido; janela e monitor responsáveis definidos; nenhuma
atividade crítica conflitante. Cancelar/adiar se houver destino incerto,
índice inválido/divergente, espaço insuficiente, custos de carga inaceitáveis,
locks prolongados ou falta de monitoramento. Considerar implantado apenas com
`verify` aprovado, ausência de erro de carga, plano posterior revisado e
registro do custo/benefício observado. Um laboratório pequeno prova
compatibilidade, **não** performance em produção.

O plano de reversão está em `docs/RAW_INDEX_R1_REVERSAO.md` e requer aprovação
específica; nenhuma remoção é automática.

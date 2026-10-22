# Relatório de execução — CORE V1

Data de homologação local: 2026-10-22. Branch `codex/core-v1-implementation`.

## Implementado e testado localmente

- Executor Python CORE separado, guard de produção, faixas inclusivas de até
  100.000 IDs, lock, transações, falhas auditadas e ausência de rota MySQL/FULL.
- 19 testes estáticos/unitários novos passaram: `pytest
  tests/test_core_v1_static.py -q`.
- Regressão CORE anterior: `41 passed, 18 subtests passed` ao executar as
  suítes estáticas V1, Fase B, C1 e C2 conjuntamente.
- `docker compose -f homologation/core-v1/compose.yaml config --quiet`
  passou. PostgreSQL Docker 16.13 iniciou em volume próprio e `schema.sh`
  criou RAW/STAGING com fixtures sintéticas; as 31 views versionadas
  compilaram. Migrations 001/002/006 aplicadas no laboratório.
- Execução limpa no terceiro volume: eventos `6`, combos `1`, pedidos `12`,
  inscrições/reconciliação/alertas `87` linhas afetadas. Esses contadores são
  operações SQL, não quantidade de inscrições distintas.
- `20 passed` na suíte `tests/integration/test_core_v1_lab.py`: cabeçalhos,
  filhos, desconto só no cabeçalho, cancelamento/reembolso/quantidade, taxa e
  kit Ativo, Balcão, status especial, precedência de classificação, eventos
  separados, pedido temporal misto, combo incompleto/completo, idempotência,
  rederivação temporal, rollback de falha e gate fechado.
- O teste de falha confirmou lote `FAILED` auditado sem mudança da derivação
  da inscrição. Todos os containers do laboratório foram parados após teste;
  nenhum volume foi apagado.
- Nenhum comando CORE foi enviado ao `Atendimento`, Naruto ou fontes MySQL.

## Implementado com exceções identificadas

- A primeira execução sintética de inscrições falhou porque o driver Psycopg
  interpretou `%` literal no `ILIKE`; corrigido para `%%` e retestado.
- A primeira suíte de integração identificou apagamento de subtotal Magento
  na reconciliação e `NULL` indevido em pagamento Balcão; ambos corrigidos e
  retestados em volume fresco. Um teste de trigger ficou aguardando lock da
  própria fixture; o teste foi interrompido, ajustado e reexecutado.
- Os três volumes sintéticos criados para diagnóstico e rerun foram preservados
  (sem `down -v`). O resultado aceito é o do terceiro volume fresco.

## Pendente por dado/regra aprovada ou validação

- Reconciliação histórica real e cardinalidades do `Atendimento` não foram
  verificadas nesta tarefa. A cobertura sintética não aprova valores reais.
- `pedido_id NULL` não pôde ser inserido nas RAW sintéticas existentes porque
  os contratos RAW versionados declaram `id_pedido`/`order_id` NOT NULL. A
  tabela CORE e o UPSERT aceitam NULL, mas esse caminho não tem fixture da
  fonte sem alteração de contrato.
- Reprocessamento completo de dependências auxiliares antigas ainda precisa
  de mecanismo operacional/CDC antes de abrir qualquer indicador.
- Fonte de classificação de cupom Ativo, descrição de status detalhado,
  comprador Ativo, composição de combo e identidade/CPF não estão disponíveis
  ou não têm política validada. Ver `CORE_PENDENCIAS.md`.

## Sequência para futura carga supervisionada

1. Executar laboratório V1 novo conforme `homologation/core-v1/README.md`;
   parar na primeira falha. Verificar 20 cenários e resultado `WHERE FALSE`.
2. Revisar SQL/DDL/diff, planos e contratos STAGING; reconciliar exemplos
   históricos com consultas read-only e aprovar exceções.
3. Planejar janela, backup, papel mínimo, capacidade, ranges por entidade,
   revisão do artefato/commit e autorização explícita de migração no
   `Atendimento`. A migração não roda automaticamente pelo pipeline RAW.
4. Depois de migração aprovada, carregar eventos, combos, pedidos e inscrições
   em lotes <=100.000 IDs, reprocessar relacionamentos/auxiliares e validar
   contagens/finanças. Qualquer falha interrompe a sequência.
5. Manter a view de indicadores fechada até reconciliador completo de
   dependências, critérios de publicação e homologação real aprovados.

Não executar `--approve-production` nem definir `CORE_PRODUCTION_APPROVAL`
sem autorização operacional específica.

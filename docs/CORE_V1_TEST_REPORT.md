# Relatório de execução — CORE V1

Data de preparação: 2026-10-22. Branch `codex/core-v1-implementation`.

## Implementado e testado localmente

- Executor Python CORE separado, guard de produção, faixas inclusivas de até
  100.000 IDs, lock, transações, falhas auditadas e ausência de rota MySQL/FULL.
- 19 testes estáticos/unitários novos passaram: `pytest
  tests/test_core_v1_static.py -q`.
- Regressão CORE anterior: `41 passed, 18 subtests passed` ao executar as
  suítes estáticas V1, Fase B, C1 e C2 conjuntamente.
- `docker compose -f homologation/core-v1/compose.yaml config --quiet`
  passou (sintaxe, antes de subir qualquer serviço).
- Nenhum comando CORE foi enviado ao `Atendimento`, Naruto ou fontes MySQL.

## Implementado com exceções identificadas

- SQL de fatos/dimensões e regras por origem versionado, mas **ainda sem
  compilação/execução PostgreSQL neste turno**. Não declarar a CORE pronta
  para primeira carga até homologação SQL em volume V1 novo.
- Dados sintéticos C1 + extensão V1 e asserções de descontos de filhos,
  desconto só de cabeçalho, cancelamento/reembolso/quantidade, Balcão,
  classificação, evento ambíguo e pedido temporal misto estão preparados.
  Asserções de integração permanecem não executadas.
- Docker Desktop/Engine local não disponibilizou o pipe
  `dockerDesktopLinuxEngine`; iniciar a aplicação não o tornou acessível.
- Suíte de integração V1: `14 skipped` sem `CORE_V1_LAB_TEST=1`/banco isolado;
  nenhum teste SQL foi indevidamente contado como aprovado.

## Pendente por dado/regra aprovada ou validação

- Cobrir todos os 20 cenários mínimos com execução real da suíte de integração,
  incluindo idempotência, falha no meio, combos completos/incompletos e
  transição temporal. Atualmente só uma parte tem asserções automatizadas.
- Validar tipos, SQL e cardinalidade de todas as views contra PostgreSQL 16
  isolado. Ajustes encontrados no laboratório exigirão revisão antes de
  qualquer uso em produção.
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

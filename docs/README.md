# Índice da documentação

Comece pelo [README do projeto](../README.md), que traz a visão geral e o glossário.

## Vigentes

Descrevem como o sistema funciona hoje e são atualizados junto com o código.

| Documento | Cobre | Atualize quando mudar... |
|---|---|---|
| [OPERACAO.md](OPERACAO.md) | Conferir saúde, resolver falhas, rotinas | Sintomas, logs ou rotinas |
| [AUTOMACAO_LOCAL_RAW_CORE.md](AUTOMACAO_LOCAL_RAW_CORE.md) | Etapas do ciclo, linhas de log, limites | O ciclo ou suas etapas |
| [DEPLOY_SERVIDOR_SEM_DOCKER.md](DEPLOY_SERVIDOR_SEM_DOCKER.md) | Servidor, arquivos, instalação, versões | O servidor ou uma release |
| [KPIS_SALES_GROWTH.md](KPIS_SALES_GROWTH.md) | Objetivo e definição dos KPIs de crescimento de vendas | Um KPI ou uma decisão sobre eles |
| [CORE_REGRAS_DE_NEGOCIO.md](CORE_REGRAS_DE_NEGOCIO.md) | Contagem, classificação, eventos, combos | Uma regra de negócio |
| [CORE_V1_DICIONARIO.md](CORE_V1_DICIONARIO.md) | Origem e regra dos campos da CORE | Tabela, view ou campo CORE |
| [CORE_DIM_PESSOA_CONTATO.md](CORE_DIM_PESSOA_CONTATO.md) | Pessoas, CPF, chave HMAC, KPIs | Identidade ou KPIs de pessoas |
| [CORE_PENDENCIAS.md](CORE_PENDENCIAS.md) | Itens em aberto e decisões | Um item ou uma decisão |
| [STAGING.md](STAGING.md) | Views STAGING | Uma view |
| [RAW_ENTIDADES.md](RAW_ENTIDADES.md) | Comandos e funcionamento de cada tabela RAW | Uma entidade RAW |
| [GRANULARIDADE_RAW.md](../GRANULARIDADE_RAW.md) | Grão e PK das tabelas RAW | Uma tabela RAW |
| [GRANULARIDADE_STAGING.md](../GRANULARIDADE_STAGING.md) | Grão e chave das views STAGING | Uma view |
| [sql/core/v1/README.md](../sql/core/v1/README.md) | Mapa das migrações e etapas SQL da CORE | Uma migração |
| [homologation/core-v1/README.md](../homologation/core-v1/README.md) | Laboratório dos testes de integração | O laboratório |

## Referência técnica

Tratam de uma carga ou rotina específica, ainda útil quando ela é necessária.

| Documento | Use quando |
|---|---|
| [CORE_V1_OTIMIZACAO_INSCRICOES.md](CORE_V1_OTIMIZACAO_INSCRICOES.md) | For recalcular um volume grande de inscrições |

## Históricos

Registram uma fase do projeto. Não descrevem a operação atual e não são mantidos em
dia; cada um traz esse aviso no início. Alguns testes conferem o conteúdo deles, então
não os apague sem ajustar os testes.

| Documento | O que registra |
|---|---|
| [CORE_VALIDACAO_TECNICA.md](CORE_VALIDACAO_TECNICA.md) | Diagnóstico antes de criar a CORE (19/10/2026) |
| [CORE_FASE_B_MODELO.md](CORE_FASE_B_MODELO.md) | Proposta física da CORE |
| [CORE_FASE_C2_PLANO.md](CORE_FASE_C2_PLANO.md), [CORE_FASE_C2_MATRIZ.md](CORE_FASE_C2_MATRIZ.md) | Plano de reconciliação histórica |
| [CORE_V1_TEST_REPORT.md](CORE_V1_TEST_REPORT.md) | Homologação local da CORE V1 (22/10/2026) |
| [DEPLOY_D1_NARUTO.md](DEPLOY_D1_NARUTO.md) a [DEPLOY_D5_A_DIAGNOSTICO_RAW.md](DEPLOY_D5_A_DIAGNOSTICO_RAW.md) | Tentativa de implantação com Docker no Naruto, substituída pelo executor sem Docker |
| [RAW_INDEX_R1_MAGENTO.md](RAW_INDEX_R1_MAGENTO.md), [RAW_INDEX_R1_REVERSAO.md](RAW_INDEX_R1_REVERSAO.md) | Proposta de índice em `order_id`, não aplicada até 04/11/2026 |
| [homologation/core-c1/README.md](../homologation/core-c1/README.md), [homologation/raw-index-r1/README.md](../homologation/raw-index-r1/README.md) | Laboratórios locais de fases anteriores |
| [sql/core/proposed/README.md](../sql/core/proposed/README.md) | Revisão do SQL proposto, depois aplicado como primeiras migrações |

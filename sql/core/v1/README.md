# SQL da CORE V1

Há dois tipos de arquivo aqui: migrações, aplicadas uma vez, e etapas, repetidas a cada
faixa de IDs. A lista oficial está em `src/core/runner.py` (`MIGRATIONS` e `STEPS`).
Migração nova só entra no fim de `MIGRATIONS`, nunca no meio.

As regras de negócio estão em [CORE_REGRAS_DE_NEGOCIO.md](../../../docs/CORE_REGRAS_DE_NEGOCIO.md).

## Migrações

Rodam com `python -m src.core.runner migrate --approve-production`, nesta ordem:

| Arquivo | O que cria |
|---|---|
| `../proposed/001_core_ddl.sql` | Tabelas, dimensões e fatos da CORE |
| `../proposed/002_core_helpers.sql` | Funções auxiliares, como conversões defensivas |
| `006_core_v1_extensions.sql` | Colunas e extensões da V1 |
| `007_core_alerta_zero_id.sql` | Permite alerta para o `item_id=0` do Magento |
| `008_evento_produto.sql` | `core.evento_produto`, produtos de combo que são eventos no Ativo, e `core.evento_revisao` |
| `009_combo_vendido.sql` | View `core.combo_vendido`, um registro por combo vendido |
| `015_inscricao_removida.sql` | `core.inscricao_removida_origem`, inscrições apagadas na origem |
| `017_inscricao_fora_kpi_pessoas.sql` | View `core.inscricao_fora_kpi_pessoas` |

`008_dim_pessoa_contato.sql` tem aplicação própria, por `src.core.person_dimension`
([pessoas](../../../docs/CORE_DIM_PESSOA_CONTATO.md)).

## Etapas

Rodam por faixa de IDs, nesta ordem dentro de cada escopo:

| Escopo | Arquivo | O que faz |
|---|---|---|
| `events` | `010_eventos.sql` | Carrega `dim_evento` |
| `events` | `011_evento_map.sql` | Carrega `evento_source_map` |
| `events` | `013_invalidate_event_dependents.sql` | Marca para recálculo as inscrições do evento alterado |
| `combos` | `012_combos.sql` | Carrega `dim_combo` |
| `combos` | `014_invalidate_combo_dependents.sql` | Marca para recálculo as inscrições do combo alterado |
| `orders` | `020_pedido_magento.sql` | Pedidos Magento |
| `orders` | `021_pedido_ativo.sql` | Pedidos Ativo |
| `orders` | `022_invalidate_order_dependents.sql` | Marca inscrições de pedidos que mudaram |
| `orders` | `061_alertas_pedido.sql` | Alertas de qualidade de pedidos |
| `inscriptions` | `030_inscricao_base.sql` | Base das inscrições das duas origens |
| `inscriptions` | `040_inscricao_ativo.sql` | Status, valor e classificação do Ativo |
| `inscriptions` | `041_inscricao_magento.sql` | Status, valor e classificação do Magento, por bundle pai |
| `inscriptions` | `050_reconciliacao_pedidos.sql` | Consolida nos pedidos os totais das inscrições |
| `inscriptions` | `060_alertas.sql` | Alertas de qualidade de inscrições |

O ciclo horário não roda os escopos `events` e `combos`: `013` invalidaria todas as
inscrições. As datas e a união de eventos ficam a cargo de `src/core/event_sync.py`, uma
vez por dia. `016_combo_atribuicao_ativo.sql` é aplicado por `src/core/combo_attribution.py`.

## Somente leitura

| Arquivo | Uso |
|---|---|
| `900_validacao_readonly.sql` | Validações da carga |
| `910_combo_candidate_readonly.sql` | Candidatos a combo |
| `920_pessoas_hoje_readonly.sql` | Lista de pessoas do dia. Contém dados pessoais: não anexe a saída ao repositório |

## Dados

| Arquivo | Conteúdo |
|---|---|
| `data/evento_sku_curadoria_20261104.csv` | Quais eventos Ativo unir por SKU quando as datas divergem |
| `data/evento_unificacao_20261028.csv` | Unificação de eventos de 28/10/2026, aplicada por `src/core/event_unification.py` |

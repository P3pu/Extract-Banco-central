# CORE — Fase B: proposta física para aprovação

Status: **proposta não implantada** (2026-10-19). Nenhum SQL deste diretório foi
executado. Fonte de verdade desta revisão: `CORE_VALIDACAO_TECNICA.md`, consultas
da Fase A, views versionadas, prompt CORE v1 e dicionário CORE v1 (abas `Campos
CORE`, `Regras Negocio`, `Pendencias`, `Testes Aceite`). O dicionário é proposta,
não prova de disponibilidade na STAGING. Divergências da Fase A prevalecem.

## Modelo e grão

| Entidade | Chave natural / PK | Relacionamentos e nulabilidade |
| --- | --- | --- |
| `fato_pedido` | `UNIQUE(origem,pedido_id_origem)` / `pedido_key` | `comprador_key` opcional; nunca unir vendas de origens distintas |
| `fato_inscricao` | `UNIQUE(origem,inscricao_id_origem)` / `inscricao_key` | `pedido_id_origem` preservado, `pedido_key`, `evento_key`, `participante_key`, `combo_key` opcionais |
| `dim_evento` | `evento_key`; seed único `(seed_origem,seed_evento_id)` | um evento por ID original até união manual validada; SKU não é único |
| `evento_source_map` | `(origem,evento_id_origem)` | FK ao evento; união entre fontes só revisada, nunca por similaridade implícita |
| `dim_pessoa` | `pessoa_key`; token CPF único apenas quando validado | sem CPF em claro; sem unificação por nome |
| `pessoa_source_map` | `(origem,tipo_identificador,id_pessoa_origem)` | `Usuario`, `UsuarioBalcao`, `Customer` são namespaces diferentes |
| `dim_combo` | `(origem,combo_id_origem)` / `combo_key` | Ativo ID/nome apenas; quantidade prevista NULL até composição validada |
| `core_etl_execucao`, `core_alerta_qualidade` | IDs técnicos | histórico de lotes e exceções sem PII |

O DDL proposto é `sql/core/proposed/001_core_ddl.sql`; conversões defensivas
estão em `002_core_helpers.sql`. `003_core_upserts.sql` prepara dimensões,
combos e pedidos por lote. `005_core_inscricao_base_upsert.sql` preserva o grão
de inscrição com atributos seguros e métricas derivadas NULL. As fórmulas
individuais de `004_core_inscricao_candidates.sql` são consultas de revisão,
**não** um UPSERT final. Isso é deliberado: sem os gates abaixo, materializar
valores finais atribuiria descontos/status indevidamente. `NUMERIC(20,4)` é usado para dinheiro,
`BIGINT` para IDs CORE e originais, `TIMESTAMP` para datas sem fuso comprovado
na origem. Nenhum timestamp de origem é promovido a data de pagamento.
As colunas `*_original` guardam texto Ativo que falhe no parsing; não se
substitui NULL por zero. Não há FK `fato_inscricao.pedido_id_origem` obrigatória,
porque há 96.214 inscrições órfãs Ativo no diagnóstico.

## Dependências da RAW/STAGING — scripts a preparar antes da carga integral

1. `sa_cupom_desconto`: extrair, por PK e reconciliação dos IDs usados em
   `raw.ativo_cupom_desconto_item`, pelo menos `id_cupom_desconto` e
   `en_cupom_classificacao`. Criar RAW e view 1:1 de cabeçalho; não derivar
   Grupos de outros valores do enum. Até lá, Grupos por categoria/código é
   apenas classificação **parcial**; sinalizar `CLASSIFICACAO_CUPOM_AUSENTE`.
2. `sa_status_detalhado`: snapshot de 17 linhas com `id_status_detalhado`,
   `id_pedido_status`, `status`, `tipo`, `ativo`. Não aplicar descrições com
   `tipo='pedido'` à inscrição sem regra validada. Código 17 permanece
   indeterminado. Lookup ausente não impede guardar código original.
3. `sa_pedido.id_usuario`: ampliar contrato/fonte RAW/STAGING do pedido Ativo
   e executar backfill reconciliado somente em fase aprovada. Não copiar
   `inscricao.usuario_id` para `comprador_key`; 445/4.015 inscrições da amostra
   tinham usuário distinto do pedido. Magento `magento_pedido.cliente_id` é
   candidato a comprador; não a participante.
4. Combo: ampliar `sa_combo.nr_qntprovas` e extrair
   `sa_combo_evento_categoria` com contrato de PK/colunas a confirmar.
   `nr_qntprovas=0` apareceu em 566/1.000 pedidos combo recentes e não significa
   combo completo. Ainda não computar `qtd_combos_vendidos` nem ticket por combo.
5. CPF: aprovar validação de dígitos, HMAC-SHA256 com segredo externo,
   acesso restrito e evidência de papéis. Não preencher `dim_pessoa`/maps na
   carga base enquanto a política faltar. `magento_item_cliente` ambíguo não
   define participante. Nenhum CPF bruto vai à CORE ou logs.
6. Categoria Magento: `categoria_origem` é ID de `attribute_set_id`, não
   categoria textual. Persistir ID como texto de origem; nome NULL até fonte
   textual validada. `campanha_salesforce_id` Ativo não é SKU Magento por
   presunção. Evento 22054 Ativo é teste curado e preservado na dimensão.
7. `dt_pagamento` Ativo não comprova recebimento: 575.900 pagamentos
   `RECUSADO` têm data preenchida na RAW. `nr_valor_pago` nem foi extraído.
   Nenhum KPI de caixa ou data efetiva de pagamento nesta versão.

Os contratos de extração existentes estão em `src/sources/ativo/`, os loaders
em `src/pipeline/`, os DDL RAW em `sql/postgres/` e as 31 views em
`sql/staging/`. A proposta separável de dependências fica em
`sql/core/proposed/000_missing_sources.sql`; ela **não** integra ainda o CLI
RAW nem popula tabelas. O gate exige validar tipos/PK na origem e testes de
extração antes de adicionar as novas entidades ao CLI.

## Política financeira e de status proposta

- Pedido Magento: bruto `subtotal`; líquido `subtotal + desconto`; cobrado
  `grand_total`; residual `grand_total - líquido`, com frete e imposto separados.
  Residual não é taxa de serviço pura. O cabeçalho aparece uma vez por pedido.
- Inscrição Magento: bundle pai `item_id` preserva a linha. Não soma pai e
  filhos. Filhos têm prioridade para desconto, pai só se filhos não tiverem
  desconto. Diferença entre desconto do cabeçalho e descontos identificados
  fica não atribuída. Em exceção, `valor_liquido_itens` pode existir, mas
  `valor_liquido_inscricao` final fica NULL. Quantidades canceladas,
  reembolsadas ou `qty_ordered != 1` são alerta; cancelamento total exclui,
  parcial/estorno não são convertidos em inscrição íntegra.
- Ativo: bruto = `preco`. Líquido = `GREATEST(0,preco-desconto_individual-
  valor_kit)` só com todos os operandos válidos. `desconto_individual` é texto;
  vírgula decimal única pode ser normalizada, separador ambíguo é erro. Taxa
  de serviço = `inscricao.taxa`, fora da receita. Pedido Ativo só recebe
  agregados quando a cobertura das inscrições for demonstrada; caso contrário
  totais do pedido ficam NULL, não zero. `ativo_pedido.taxa` não é taxa individual.
- Cancelamento explícito de pedido ou inscrição vem antes de pagamento
  confirmado/presumido. Ativo pedido 2 confirma pagamento, pedido 1/local 2
  permite contagem legado mas não confirma recebimento. Status individuais
  5–8 excluem; 0 e 9–13 são candidatos aceitos quando tipo/semântica confirmados;
  1, 14, 15, 17 e pendências 2–4 ficam indeterminados. Até resolver lookup,
  somente 0 pode ser aceito automaticamente, com essa restrição documentada.
- Magento `canceled` em `state` ou `status` exclui. Pares contraditórios
  (`new/approved`, `processing/canceled`) geram alerta; os não cancelados
  contraditórios ficam indeterminados. Pares estáveis `processing/approved/
  complete` confirmam. `new`/`pending` sem conflito não confirmam.
- Regra de evento ocorrido: apenas inscrição pendente, não cancelada/não teste,
  sem status especial nem reembolso, com data válida `< CURRENT_DATE`, recebe
  `pagamento_presumido`; não altera status original nem promove o pedido todo.
  Recalcular em cada execução mesmo sem atualização RAW. Confirmado e presumido
  são colunas separadas. Mês financeiro = mês do pedido, não mês de caixa.
- `contabiliza_bruto` inclui inscrição comercial real nova/pendente/aprovada,
  exclui cancelamento/teste e trata status/quantidade ambíguos como NULL.
  `bruto_comercial_apuravel` no pedido Magento exige não haver mistura de
  itens teste/cancelados/ambíguos; não alocar header a subconjunto.

## Cobertura de regras e testes de aceite

| Regras / testes | Evidência na proposta | Estado para liberação |
| --- | --- | --- |
| ID-01, INS-01/02, T01/02/14 | UNIQUE `(origem,id)`, UPSERT por lote, teste de repetição | SQL preparado; execução pendente |
| T03, T12, T17 | FKs opcionais, IDs de origem, map por fonte, teste curado 22054 | DDL preparado; recálculo pendente |
| FIN-01/02/04, T04–T07, T18 | header 1x, pais/filhos pré-agregados, diferença não atribuída | Query de aceite preparada; carga pendente |
| FIN-05/06, T08/09 | parser defensivo, status e taxa individual Ativo | status lookup e cobertura ainda pendentes |
| FIN-07/08/09, T10/11 | flags de bruto/confirmado/presumido por inscrição | validar subset e calendário; MART fora do escopo |
| CLS-01–05 | Grupos > Cortesia > Site; cupom, categoria, etiqueta | Grupos Ativo incompleto sem cabeçalho cupom |
| ID-02/03/04, T13/15 | maps, token HMAC, categoria-ID preservada | HMAC/papéis bloqueados; evento sem união automática |
| COM-01/02 | `dim_combo` Ativo ID/nome, previsão NULL | composição e ticket combo bloqueados |
| BI-01, ETL-01–03, T16/19/20 | período pedido, lotes, revisão histórica e testes read-only | orquestração/agendamento não implementados |

Os testes T10, T17 e T18 referem-se à MART no dicionário. Nesta fase somente
as condições CORE/SQL de reconciliação podem ser revistas; a MART continua
inexistente. O inventário real da Fase A confirmou 176/176 colunas das oito
views do Excel (o valor `166?` no prompt não é o total verificado).

## Pendências classificadas

**Bloqueantes para carga completa ou afirmação do indicador:** política HMAC
e papéis; classificação cupom Ativo completa; semântica de status especial;
financeiro individual dos casos Magento com desconto header, qty parcial ou
reembolso; composição de combo/ticket combo; prova de cobertura do total Ativo;
performance e reconciliação histórica antes de rotina 3x/dia.

**Não bloqueantes para estrutura e fato conservador:** eventos não mapeados,
órfãos, categoria-ID Magento, comprador/participante NULL, datas/valores Ativo
inválidos com alerta, ausência de data de caixa, SKU repetido. Esses registros
devem ser preservados; não entram automaticamente em indicadores não apuráveis.

## Ordem de implantação futura e reversão

1. Aprovar este modelo e as decisões bloqueantes. Fazer backup verificável,
   registrar checksum/versão dos scripts, ambiente de homologação e plano de
   permissões (dimensões de pessoa separadas do BI).
2. Integrar dependências RAW/STAGING em mudanças separadas, com metadados MySQL
   revalidados, carga de teste, reconciliação de antigos e testes de nulidade.
   Não recriar views a cada atualização.
3. Em homologação, aplicar 001 e 002; rodar smoke tests de catálogo/constraints.
   Carregar dimensões/maps, pedido e inscrição base por lotes limitados; aprovar
   separadamente os UPSERTs derivados e alertas após resolver os gates. Não
   abrir transação por todo o histórico.
4. Executar testes read-only `sql/core/proposed/900_core_acceptance_readonly.sql`
   e comparar contagens/valores com a Fase A. Fazer dois ciclos sem mudanças e
   um ciclo com alteração histórica conhecida. Inspecionar `EXPLAIN` dos lotes;
   não rodar joins não limitados que já causaram `DiskFull`.
5. Só depois autorizar produção. Operação futura: 06:00, 12:00, 18:00
   `America/Sao_Paulo`; reconciliar IDs novos, pendentes, eventos recentes,
   órfãos e blocos históricos rotativos. Nenhum scheduler foi criado aqui.

Reversão: interromper cargas, conservar snapshot/backup e lotes/alertas para
auditoria; restaurar apenas as tabelas CORE afetadas ou o schema CORE a partir
do backup após confirmar ownership e janela. Nunca usar `DROP SCHEMA CASCADE`
como rollback automático; as mudanças RAW/STAGING têm rollback próprio e
dependências de leitura. Falha parcial de lote: transação por entidade/lote,
marcar `FAILED`, corrigir origem/regra e repetir o mesmo intervalo com UPSERT.

**Pedido de autorização futura deve listar explicitamente** scripts/versões,
ambiente, lotes, janelas, critérios de aceite e responsável pelo rollback.
Esta proposta não constitui autorização para executar DDL ou carga.

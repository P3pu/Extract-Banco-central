# CORE — validação técnica pré-DDL

Data: 2026-10-19. Escopo: diagnóstico somente leitura de `Atendimento`, MySQL Ativo,
SQL versionado e critérios do `Dicionario_de_Dados_CORE_v1.xlsx`. Nenhuma carga,
migração ou alteração de RAW/STAGING/CORE foi executada. Os números abaixo são
contagens agregadas, sem CPF, nome, e-mail ou identificador individual de pessoa.

## Resultado executivo

- O PostgreSQL `Atendimento` está acessível com `transaction_read_only=on`.
- O catálogo contém 38 tabelas RAW (incluindo duas técnicas), 31 views STAGING
  e nenhum objeto CORE. As oito views do inventário Excel têm **176/176**
  colunas com nome, posição e tipo exatamente iguais ao `information_schema`.
- A CORE conservadora pode preservar os grãos de pedido e inscrição. Ela **não**
  deve preencher identidade, classificação completa de Grupos, líquido individual
  não conciliado, combo completo ou data de recebimento sem as dependências abaixo.
- A STAGING Ativo possui 12.506.395 inscrições, das quais 96.214 não encontram
  pedido na RAW e 15 não encontram evento. A STAGING Magento possui 2.044.545
  inscrições bundle, 14.543 sem evento mapeado e 3.832 com cliente ambíguo.
- Uma junção ampla de pedidos Magento com clientes falhou por falta de memória
  compartilhada temporária no servidor (`DiskFull`). As demais verificações
  relacionais foram limitadas a amostras indexadas; não interpretar amostra como
  prova de todo o histórico.

As consultas PostgreSQL reproduzíveis estão em `sql/core_phase_a_readonly.sql`.
Executar cada bloco isoladamente no pgAdmin, de preferência fora da janela de carga.

## Uso das 31 views STAGING

| View | Uso possível na CORE | Limite ou cuidado |
| --- | --- | --- |
| `magento_option_label` | Rótulos EAV de modalidade/tamanho | `option_id` não é necessariamente único; `magento_produto` escolhe um rótulo. |
| `magento_pedido` | Base 1:1 de `fato_pedido` | Cabeçalho financeiro só uma vez por pedido. |
| `magento_item_pedido` | Quantidade, cancelamento, reembolso e desconto pai/filho | Pais e filhos têm grãos distintos; não somar valores replicados. |
| `magento_produto` | Categoria-ID, modalidade, tamanho e pistas de evento/combo | `conjunto_atributos_id` é numérico, não categoria textual. |
| `magento_produto_evento_mapeamento` | Qualidade do vínculo produto→evento | Não forçar candidatos ambíguos. |
| `magento_evento` | Base de evento Magento resolvido | Não inclui eventos sem vínculo resolvido. |
| `magento_cliente` | Documento do cadastro do comprador candidato | `taxvat` pode não ser CPF e papel individual deve ser provado. |
| `magento_endereco_cliente` | Apoio futuro a geografia | Endereços 1:N e PII; desnecessário no primeiro fato. |
| `magento_item_cliente` | Associação item–cliente candidata | 3.832 inscrições têm cliente ambíguo; não inferir participante. |
| `magento_cliente_empresa` | Contexto empresarial | Não equivale sozinho à classificação Grupos. |
| `magento_pedido_regra` | Sinais de Grupos/Cortesia por etiqueta | 1:N por pedido; usar `EXISTS` ou pré-agregação. |
| `magento_bundle_componente` | Desconto dos filhos, modalidade e tamanho | 1:N por bundle; agregar antes de juntar ao fato. |
| `magento_inscricao` | Base 1:1 do bundle pai | Não traz quantidade cancelada/reembolsada do pai; consultar `magento_item_pedido`. |
| `ativo_pedido` | Base 1:1 de `fato_pedido`, status, combo | Falta `sa_pedido.id_usuario` na extração atual. Datas textuais. |
| `ativo_evento` | Base de evento Ativo | `campanha_salesforce_id` não é SKU Magento comprovado. Data textual. |
| `ativo_modalidade` | Rótulo da modalidade | Usar ID original e sinal de mapeamento da inscrição. |
| `ativo_categoria` | Categoria textual e `valor_kit` | O kit não é taxa; validar aplicação e `NULL`. |
| `ativo_tamanho_camiseta` | Rótulo do tamanho | Normalização exige regra aprovada. |
| `ativo_usuario` | Cadastro ligado a `inscricao.usuario_id` | Tem `documento`; papel de participante precisa confirmação funcional. |
| `ativo_usuario_balcao` | Cadastro separado ligado a `usuario_balcao_id` | Mesmo nome físico `id_usuario`, outra namespace; não fundir por ID. |
| `ativo_forma_pagamento` | Descrição da forma de pagamento | Apoio; não confirma recebimento. |
| `ativo_pagamento` | Status, registro e `data_pagamento` por pagamento | Potencial 1:N por pedido; data sozinha não prova pagamento. |
| `ativo_transacao` | Sinais de cancelamento de transação | Potencial 1:N por pagamento; não juntar diretamente ao fato. |
| `ativo_pedido_produto` | Itens complementares do pedido | 1:N; não representa automaticamente inscrição/combos. |
| `ativo_endereco_pedido` | Apoio geográfico futuro | 1:N e PII; não selecionar endereço arbitrário. |
| `ativo_cidade` | Geografia futura | Grão pela PK física `id`, não por `cidade_id`. |
| `ativo_estado` | Geografia futura | Grão pela PK física `id`, não por `estado_id`. |
| `ativo_pais` | Geografia futura | Não necessário para fatos principais. |
| `ativo_combo` | ID e nome do combo | Não contém composição nem quantidade prevista. |
| `ativo_cupom` | Código do cupom individual e ID do cabeçalho | Carga RAW histórica seletiva; classificação do cabeçalho ausente. |
| `ativo_inscricao` | Base 1:1 de `fato_inscricao` | Preserva órfãos; desconto é `VARCHAR`, datas de evento/pedido são `TEXT`. |

## Dependências e resultados por tema

### Cupom Ativo e status detalhado

**Bloqueante para classificação completa de Grupos:** `sa_cupom_desconto` existe
no MySQL, PK `id_cupom_desconto`; `en_cupom_classificacao` é um `ENUM` que inclui
`Grupos`. Há 26.529 cabeçalhos de cupom, 1.755 classificados `Grupos` e 9.497
com classificação NULL. `sa_cupom_desconto_item.id_cupom_desconto` fornece a
ligação. Porém não existem `raw.ativo_cupom_desconto` nem view correspondente.
Os sinais alternativos (prefixo `GR`, categoria textual) não substituem a
classificação ausente. Incluir extração seletiva dos cabeçalhos referenciados,
com reconciliação, requer aprovação de mudança na RAW/STAGING.

**Bloqueante parcial para descrição e regras especiais:**
`sa_status_detalhado` existe no MySQL, com 17 linhas e colunas
`id_status_detalhado`, `id_pedido_status`, `status`, `tipo`, `ativo`. Não é
extraída para RAW. Os códigos 9–13 têm `tipo='pedido'`; o código 17 é
`Estorno Parcial`, `tipo='inscricao'`. Na RAW de inscrições há 12.477.533
registros com código 0, 12.692 com 5, 14.072 com 6 e 2.071 com 17;
9–13 não apareceram nessa distribuição. Não aplicar cegamente descrições de
status de pedido à inscrição. A descrição pode ficar NULL até carregar o lookup;
o código 17 deve permanecer exceção de elegibilidade.

### Financeiro Magento

Os quatro pedidos do aceite foram encontrados por `pedido_id`, sem usar dados de
cliente. A fórmula `subtotal + desconto` e o residual
`valor_total - (subtotal + desconto)` dão:

| Pedido | Líquido cabeçalho | Desconto filhos | Desconto pai | Residual operacional | Diagnóstico |
| --- | ---: | ---: | ---: | ---: | --- |
| 166688 | 59,0000 | 0 | 0 | 14,2100 | Pai e três filhos somam 59 cada nível; não duplicar. |
| 1673612 | 159,8400 | 39,9600 | 0 | 19,9800 | Dois bundles; desconto dos filhos reconcilia o cabeçalho. |
| 1673646 | 125,0128 | 0 | 0 | 26,0000 | Desconto −134,9972 só no cabeçalho; líquido individual final indeterminado. |
| 1673884 | 119,9200 | 29,9800 | 0 | 14,9900 | Residual não é prova de taxa de serviço pura. |

No histórico RAW há 2.044.545 bundles pai, **66** com `qty_ordered != 1`,
227.951 com `qty_canceled > 0` e 482 com `qty_refunded > 0`.
Logo, a identidade de uma inscrição por `item_id` preserva o grão de linha,
mas não autoriza tratar toda linha como uma inscrição íntegra e elegível.
Em amostra dos 50 mil bundles pai de maior `item_id`, 64 não acharam pedido
na RAW. O status Magento também requer precedência: existem pares
`canceled/approved` (251), `processing/canceled` (115) e `new/approved` (488).

### Comprador, participante e CPF

As três views de cadastro expõem `documento`. Cobertura completa do campo:
`ativo_usuario` 3.488.490/3.756.947; `ativo_usuario_balcao`
1.516.768/1.517.953; `magento_cliente` 1.187.524/1.197.021.
Validação de dígitos verificadores em **50 mil IDs recentes por cadastro**,
sem retornar valores: CPF válido 48.785 (`ativo_usuario`), 43.076
(`ativo_usuario_balcao`) e 47.613 (`magento_cliente`). São amostras, não
cobertura histórica nem prova do papel da pessoa.

No Magento, 49.993/50.000 pedidos recentes têm `customer_id` e o cadastro
correspondente, forte candidato a **comprador**. A relação item–cliente não
declara papel e pode ser ambígua; não promover automaticamente a participante.
No Ativo, todas as 12.506.395 inscrições têm `id_usuario` e 6.049.497 também
têm `id_usuario_balcao`. A origem MySQL `sa_pedido` possui `id_usuario`, mas a
RAW/STAGING do pedido não o extraem. Em 1.000 pedidos recentes da origem,
houve 4.015 inscrições, das quais 445 tinham `id_usuario` diferente do pedido.
Isso reforça que comprador e inscrito não devem ser equiparados; o papel exato
de `id_usuario_balcao` ainda precisa de confirmação funcional. Não ativar
unificação entre sistemas antes de validar CPF, papéis e desenho de HMAC.

### Combos

O MySQL contém `sa_combo.nr_qntprovas` e
`sa_combo_evento_categoria(id_combo,id_evento,fl_obrigatorio,...)`; esses dados
de composição não estão na RAW/STAGING. Há 1.305 combos e 9.680 linhas de
`sa_combo_evento_categoria` para 1.280 IDs de combo. Em 1.233/1.305 combos,
o número de linhas de configuração difere de `nr_qntprovas`, logo não é um
substituto direto. Dos 1.000 pedidos combo mais recentes da origem, 566 têm
`nr_qntprovas=0`; nos outros 434, a quantidade de inscrições coincidiu com o
número previsto, mas **não** foram verificados evento/categoria, integridade
histórica nem semântica dos combos variáveis. `dim_combo` pode guardar ID/nome;
`qtd_inscricoes_previstas` e venda completa permanecem pendentes.

### `dt_pagamento` Ativo

`staging.ativo_pagamento.data_pagamento` existe como `TEXT`; a origem é
`sa_pedido_pagamento.dt_pagamento` (`DATETIME`). A RAW não extrai
`nr_valor_pago`, embora a coluna exista na origem. No conjunto RAW completo:

| `fl_status` | Pagamentos | Com `dt_pagamento` preenchida |
| --- | ---: | ---: |
| `CONFIRMADO` | 4.118.305 | 4.112.387 |
| `PENDENTE` | 309.908 | 2.991 |
| `RECUSADO` | 1.075.313 | 575.900 |
| vazio | 427.476 | 760 |

Uma data em **575.900 pagamentos recusados** impede usar `dt_pagamento` como
prova isolada de recebimento. O vínculo é `pagamento.id_pedido → pedido.id_pedido`;
o contrato da origem não declara unicidade de `id_pedido`. Amostras de 100 mil
pagamentos antigos e 100 mil recentes mostraram um pagamento por pedido em
cada recorte, o que **não prova** 1:1 no histórico completo. Não adicionar data
de caixa à CORE sem validar status, valor pago, transações e múltiplas tentativas.

### Órfãos, status e atualização

`staging.ativo_inscricao` preserva os 96.214 IDs de pedido órfãos; em amostra
recente de 100 mil inscrições, 90 eram órfãs, 36.695 tinham pedido status 5 e
2.141 eram pendentes de balcão (`status=1`, `local=2`). Nenhuma dessas contagens
é, por si, medida de inscrição elegível. `staging.magento_inscricao` preserva
14.543 casos sem evento mapeado e 3.832 com cliente ambíguo. Flags e IDs de
origem precisam continuar na CORE.

A RAW usa incremental por PK em várias entidades Ativo/Magento e reconciliação
com janela, de modo que mudanças antigas e órfãos recuperáveis não estão
garantidos para uma rotina automática. Regras com `CURRENT_DATE` precisam de
reavaliação mesmo sem alteração da fonte. A classificação de evento de teste
por ID curado e o vínculo entre eventos de origens diferentes **não** foram
executados automaticamente nesta validação.

## Confronto com `Testes Aceite`

| Testes | Estado antes do DDL | Evidência ou dependência |
| --- | --- | --- |
| T01–T02 | Pendente | CORE ainda não existe; grãos/PKs de origem comprovados no catálogo. |
| T03 | Parcial | 96.214 órfãos Ativo e 14.543 eventos não mapeados Magento; preservação CORE a testar. |
| T04–T07 | Insumos verificados | Quatro pedidos financeiros conferidos; transformações CORE ainda não implementadas. |
| T08–T09 | Parcial | Códigos/status e balcão medidos; precedência e resultado CORE ainda não testados. |
| T10–T11 | Pendente | MART inexistente; pago presumido e exclusões ainda sem transformação. |
| T12–T13 | Parcial | Ambiguidade e CPF agregado conhecidos; nenhuma fusão de evento/pessoa autorizada. |
| T14 | Pendente | Reprocessamento CORE ainda não existe. |
| T15 | Verificado na fonte | `magento_inscricao.categoria_origem` é `INTEGER`; regra CORE a testar. |
| T16 | Pendente | `EXPLAIN` disponível; carga 3x/dia não deve varrer todo histórico. |
| T17–T18 | Pendente | MART inexistente; não multiplicar cabeçalho na futura transformação. |
| T19 | Verificado | 176/176 colunas, posições e tipos nas oito views inventariadas. |
| T20 | Pendente | Reconciliar alterações antigas e pedidos ausentes requer desenho adicional. |

## Pendências para decisão

**Bloqueantes para seus respectivos campos/regras (não para armazenar o fato
conservador com NULL e alerta):**

1. Extrair `sa_cupom_desconto` para aplicar o sinal completo de Grupos.
2. Definir semântica do status individual, sobretudo `tipo='pedido'` e código 17;
   extrair lookup se o texto do status for necessário.
3. Extrair/validar `sa_pedido.id_usuario` para comprador Ativo; provar o papel de
   `magento_item_cliente` e `id_usuario_balcao` antes de preencher participante.
4. Aprovar política de CPF/HMAC e acesso antes de unir pessoas entre fontes.
5. Tratar cancelamento/reembolso parcial, `qty_ordered != 1` e desconto só no
   cabeçalho antes de afirmar líquido final por inscrição.
6. Extrair composição de combo e definir significado de `nr_qntprovas=0` antes
   de calcular venda completa/ticket por combo.
7. Não usar `dt_pagamento` como data de caixa sem regra reconciliada com status,
   valores pagos, transações e cardinalidade histórica.

**Não bloqueantes com tratamento explícito:** categoria-ID Magento numérica;
datas textuais Ativo com parsing defensivo; órfãos preservados; estado/status
Magento conflitantes sinalizados; eventos sem vínculo corporativo mantidos por
`(origem, evento_id_origem)`; geografia e endereços adiados; performance e
reconciliação como portões antes de qualquer execução periódica.

Próximo portão: revisar estes resultados e o DDL proposto. Nenhuma migração ou
backfill deve ocorrer por inferência desta análise.

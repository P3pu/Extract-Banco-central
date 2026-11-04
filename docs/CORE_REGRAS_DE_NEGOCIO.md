# CORE V1 — regras implementadas

Versão das regras: `CORE_V1_20261022` (inscrições Ativo: `CORE_V1_20261030`). A CORE está carregada no `Atendimento`
desde 23/10/2026 (migrações 001, 002, 006, 007 e 008) e é mantida pela
automação local horária (`docs/AUTOMACAO_LOCAL_RAW_CORE.md`). O executor CORE
é separado do D1/RAW e lê somente as views STAGING PostgreSQL. A view de
indicadores `core.fato_inscricao_indicadores_validos` permanece `WHERE FALSE`.

## Grão e identidade

- `fato_pedido`: `(origem, pedido_id_origem)`; protocolo Ativo = ID do pedido,
  Magento = `increment_id`. Cabeçalho financeiro entra uma vez por pedido.
- `fato_inscricao`: `(origem, inscricao_id_origem)`; Ativo = pedido_evento,
  Magento = bundle pai. Filhos não viram inscrições. Órfãs e pedido NULL ficam.
- Participante Ativo é quem corre: com `usuario_balcao_id` maior que zero, é o
  balcão (namespace `UsuarioBalcao`), e o `usuario_id` fica só como comprador do
  pedido (decisão de 03/11/2026). Sem balcão, é o `usuario_id` (namespace
  `Usuario`). ID zero conta como ausente. `participante_id_origem` Magento fica NULL; a `participante_key`
  Magento só é preenchida pela sincronização de contatos, quando o cliente do
  bundle não é ambíguo. Comprador Ativo = `sa_pedido.id_usuario` (namespace
  `Usuario`), desde 30/10/2026; nunca é copiado do participante. Quem compra
  com o próprio CPF é comprador; se aparece em inscrições de pedidos de outro
  comprador, é também participante (papel `AMBOS` na `dim_pessoa`).
- `dim_pessoa` (migração 008): CPF com dígitos válidos vira token HMAC-SHA256 e
  reúne comprador e participante, inclusive entre Magento e Ativo, numa única
  `pessoa_key`. CPF ausente ou inválido gera uma pessoa por ID de origem
  (`SOURCE_ID`). Nunca há junção por nome ou e-mail. Conflito de CPF ou fusão
  de duas `pessoa_key` interrompe a carga para revisão. CPF, nome e e-mail
  ficam só na dimensão, com preenchimento atrás do gate
  `CORE_PII_ENABLE_SYNC`. Detalhes em `docs/CORE_DIM_PESSOA_CONTATO.md`.

## Status e pagamento

- Ativo: pedido 2 = pagamento confirmado; pedido 1/Balcão 2 = elegível
  comercialmente, **não** pagamento confirmado; pedido 5 cancelado.
  Inscrição 5–8 cancelada; 0/9–13 elegível se pedido elegível; outros códigos
  pendentes. Cancelamento individual prevalece. Data de pagamento não prova
  recebimento.
- Magento: matriz fechada `state/status` da helper 002. Apenas combinação
  coerente processing/approved/complete confirma. Cancelamento prevalece.
  `new/pending` com evento anterior a `--as-of` pode ser pago presumido, com
  data de referência registrada. Isto não é recebimento bancário.
- `--as-of` entra no hash de dependências. Mudança de data exige reprocessar
  inscrições pendentes. A view de indicadores continua fechada mesmo para
  `VALIDADO`, até conciliação real e política de publicação aprovadas.

## Financeiro

- Magento: subtotal, desconto assinado e `subtotal + desconto` ficam no
  pedido; `grand_total`, frete e imposto separados. Diferença de total não é
  rotulada taxa. Filhos do bundle têm prioridade sobre pai para desconto;
  somente com conciliação ao cabeçalho e quantidade segura o líquido
  individual é preenchido. Desconto apenas de cabeçalho não é rateado.
  `qty_ordered<>1`, cancelamento parcial ou reembolso deixam líquido
  individual indeterminado. Pedido misto teste/real é sinalizado.
- Ativo: bruto = `nr_preco`; desconto textual passa por conversão defensiva;
  desconto NULL ou vazio na origem é produto sem desconto e vale 0 (regras Ativo
  `CORE_V1_20261030`); texto inválido continua pendente;
  kit = `vl_kit` da categoria; líquido = `GREATEST(0,preco-desconto-kit)`
  somente com todos componentes válidos. Taxa = `nr_taxa` individual,
  segregada do kit e da receita. `preco+taxa` é derivado, não total recebido.
  Pedido Ativo só consolida quando todas as inscrições estão carregadas, os
  status são interpretáveis e os componentes calculáveis; na perda de
  cobertura, totais voltam a NULL.

## Classificação, eventos e combos

GRUPOS > CORTESIA > SITE. Ativo aceita prefixo GR do cupom e categoria
`grupo`/`Saúde Corporativa`. Cupom não exige classificação própria (decisão de
negócio 30/10/2026): ter cupom não deixa a inscrição pendente. A classificação
do cabeçalho (`sa_cupom_desconto.en_cupom_classificacao`, via
`staging.ativo_cupom_desconto`) fica em `classificacao_cupom_ativo`; o valor
`Grupos` (individual ou do pedido) classifica a inscrição como GRUPOS. As
demais classificações são só informativas. Magento aceita prefixo GR e etiqueta de
regras; categoria numérica não é tratada como texto. Cortesia usa categoria,
etiqueta ou bruto zero somente na ausência de sinal de grupos. No Magento a
categoria é o nome do bundle vendido (decisão de 04/11/2026): nome com `cortesia`
ou `patrocinador` é CORTESIA, mesmo com valor pago. Conferido contra a planilha
do sistema do Night Run Fortaleza 2026: 2.417 de 2.417 linhas.

Combos são vendidos no Ativo e parte deles foi migrada para o Magento, com
protocolo `<id_pedido Ativo>-<n>` e um bundle `<EVENTO>COMBO<n>` por prova.
O Ativo é a origem oficial (decisão de 03/11/2026): inscrições Magento desses
protocolos ficam com `contabiliza_inscricao=false` e motivo
`COMBO_MIGRADO_ATIVO`, sem dupla contagem, e a migração é só sinalização.

Regra única para os combos do Ativo, migrados ou não: o Ativo traz uma
inscrição por prova e um `id_combo` por pedido. Pertencem ao combo todas as
inscrições do pedido, menos os produtos. O cardápio
(`sa_combo_evento_categoria`) não é usado: não acompanha etapas trocadas depois
da venda e deixava de fora 18,5 mil combos com provas legítimas (ensaio de
03/11/2026). Produtos do combo (Hoodie,
Mala tubo, Óculos, Moletom Bravus) são eventos no Ativo, sem campo que os
identifique: a lista `core.evento_produto` os mantém fora dos combos e da
contagem de inscrições (motivo `PRODUTO_NAO_INSCRICAO`) e precisa de curadoria
quando surgir produto novo.

Um pedido pode ter vários combos vendidos, então a unidade não é o pedido:
cada participante do pedido é um combo vendido (`grupo_comercial_id =
<pedido>:ativo:<id_combo>:<participante>`, regra 016). O tamanho do combo é a
quantidade mais comum de inscrições daquele `combo_id` (o nome se repete por ano
e praça, com tamanhos diferentes). Inscrições em múltiplo exato do tamanho
contam um combo por múltiplo, sufixo `:<n>` a partir do segundo, em ordem de
inscrição. Acima do tamanho sem múltiplo exato fica para revisão. Tamanho menor
que 2 não separa combos. `nr_qntprovas`
não é usado (0 nos combos Fixo). A automação recalcula os pedidos
alterados; `python -m src.core.combo_attribution --approve-production`
preenche o histórico e substitui as atribuições da antiga regra por SKU.

Magento direto (desde out/2023), fora dos protocolos migrados: cada linha com
`COMBO` no SKU é uma prova, não um combo, e cada etapa costuma vir em um pedido,
sem participante. Um combo vendido = comprador + circuito + `COMBO<n>` do primeiro
trecho do SKU (`CDE25SP1COMBO4` = circuito `CDE25SP`, etapa 1, 4 provas); a
k-ésima linha de cada etapa forma o k-ésimo combo. O Hoodie vem dentro do SKU da
etapa e não tem linha própria, então não conta, mas o valor dele não se separa do
valor da linha.

`core.combo_vendido` (migração 009) tem uma linha por combo vendido com canal
(`ATIVO`, `MAGENTO`), sinais `migrado_magento`, `revisar` e `motivo_revisao`, combo, pedido, data, valores e
`contabiliza`, base para combos vendidos, faturamento e ticket médio. Combo com
`revisar=true` fica com `contabiliza=false` até ser revisto. `motivo_revisao`, com
os motivos separados por `+`: `TAMANHO` (acima do tamanho sem formar outro combo),
`VALOR` (inscrição não cancelada acima de R$ 2.000, caso dos combos 408 e 437 de
2017, de R$ 8.700 e R$ 10.000 por prova), `PRODUTO` (evento em
`core.evento_revisao`, como o Kit Vip), `SEM_NUMERO` (SKU Magento sem `COMBO<n>`),
`ETAPAS_INCOMPLETAS` (circuito Magento com menos etapas que provas, como
`CDE24SP1COMBO2`, em que a outra prova tem outro SKU) e `SEM_COMPRADOR`. A flag vale
só para o combo: as inscrições continuam na fato. Em todos os canais, o combo conta
se qualquer inscrição contar, porque foi vendido mesmo com uma prova cancelada, mas
o valor das canceladas não entra nos valores do combo (decisão de 03/11/2026).

Eventos nascem separados por `(origem, ID)`. A unificação entre origens só
existe por vínculo validado: o evento Magento passa a apontar para o
`evento_key` do evento Ativo em `core.evento_source_map`
(`MANUAL_VALIDADO`, com `revisado_por`/`revisado_em`), e os dois eventos
ficam `UNIFICADO_VALIDADO` na `dim_evento`. A carga de eventos não sobrescreve
esses vínculos. Regra aprovada em 28/10/2026: mesmo SKU e mesma data unificam,
ainda que o nome esteja escrito de outra forma (patrocinador, cidade abreviada,
ano, edição), desde que haja um único melhor evento Ativo e que não seja
"Arena" só de um lado. Empates, datas diferentes e casos "Arena" ficam
separados até revisão manual. Os 482 vínculos aplicados estão em
`sql/core/v1/data/evento_unificacao_20261028.csv` e são aplicados ou
revertidos por `python -m src.core.event_unification plan|apply|revert`. Apenas o evento Ativo 22054 tem
evidência versionada de teste; outros precisam de curadoria. `dim_combo`
recebe ID/nome Ativo, mas composição e quantidade prevista permanecem NULL.
Não há cálculo confiável de combos vendidos/ticket até validação de composição
e atribuição de cada inscrição.

## Estado da derivação

Cada inscrição termina `VALIDADO` ou `PENDENTE`; `PENDENTE` significa falta de
prova, não erro.

- Ativo fica `PENDENTE` com pendência financeira, status não interpretável,
  classificação pendente sem sinal de grupos ou elegibilidade desconhecida.
- Magento fica `PENDENTE` com status `INDETERMINADO`, quantidade ambígua,
  desconto não conciliado, evento não mapeado ou pedido não encontrado.
- A derivação grava `derivado_de_hash` (conteúdo) e
  `dependencias_hash_snapshot` (status, finanças, auxiliares, regra e data de
  referência). Divergência em qualquer um, versão de regra diferente ou
  `derivado_de_dependencias_hash` NULL (inscrição invalidada) provoca nova
  derivação.

## Alertas de qualidade

`core.core_alerta_qualidade` guarda apenas regra, severidade e ID numérico de
origem: `STATUS_CONTRADITORIO`, `STATUS_ESPECIAL`, `CANCELAMENTO_PARCIAL`,
`REEMBOLSO`, `QTD_BUNDLE`, `DESCONTO_CABECALHO`, `DESCONTO_INVALIDO`,
`CUPOM_HEADER_AUSENTE`, `EVENTO_SEM_MAPA`, `ORFAO_PEDIDO`, `COMBO_COMPOSICAO`
e `DATA_INVALIDA`.

## Mesmo SKU e pessoas fora dos KPIs (04/11/2026)

Mesmo SKU é a mesma prova, e a data do Magento prevalece, inclusive nas inscrições
do Ativo. Uma vez por dia, `src/core/event_sync.py` une os eventos e atualiza as
datas de `dim_evento`. Se os eventos Ativo do SKU têm datas diferentes, só une com
curadoria em `sql/core/v1/data/evento_sku_curadoria_20261104.csv`, porque há SKU
repetido em cidades diferentes; sem ela, o SKU sai no log como `revisar`.

Inscrição processada antes de chegar o cadastro é religada no mesmo passo diário
(`relink_missing`). A que não dá para ligar, ou tem CPF inválido, aparece em
`core.inscricao_fora_kpi_pessoas` com `flag_fora_kpi_pessoas` e `motivo`. Ela
continua em inscritos e faturamento, mas não nos KPIs de pessoas.

## Eventos abertos e inscrições removidas (04/11/2026)

A reconciliação por janela olha só `dt_pedido` dos últimos 30 dias. Por isso, uma
vez por dia a automação também relê pedidos e inscrições de eventos com data a
partir de 30 dias atrás (`src/pipeline/ativo_eventos_abertos.py`), gravando e
levando à CORE só o que mudou. Inscrição que não está mais na origem, confirmada
pela PK, entra em `core.inscricao_removida_origem`: a linha continua na RAW e na
fato, mas fica com `motivo_elegibilidade='REMOVIDA_NA_ORIGEM'` e não conta. Se
voltar à origem, a marca sai. Pedido antigo de evento encerrado há mais de 30 dias
continua fora da releitura diária: só uma releitura completa o alcança.

## Reprocessamento e segurança

Ranges têm no máximo 100.000 IDs inclusivos. Eventos, combos e pedidos
reprocessados invalidam inscrições afetadas. Desde 28/10/2026, a invalidação
por pedido (`022`) atinge só inscrições de pedidos cujo `conteudo_hash` mudou
na própria transação e da mesma origem; antes, faixas inteiras de pedidos de
ambas as origens eram invalidadas sem nova derivação. Alterações em cadastros auxiliares
(categoria, cupom, regra, filho de bundle) exigem reprocessamento da faixa de
inscrições afetada; a reconciliação deve concluir antes de qualquer abertura
da view. O runner usa lock global, transações, auditoria, hash de dependências
e bloqueio de `Atendimento` sem dois sinais explícitos de aprovação. Não há
rota FULL nem leitura MySQL na CORE. A automação local horária leva à CORE só
os IDs RAW alterados, atualiza os cadastros RAW uma vez por dia e recusa rodar
se a view de indicadores estiver aberta.

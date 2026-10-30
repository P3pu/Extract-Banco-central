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
- Participante Ativo é preservado com namespace `Usuario` ou `UsuarioBalcao`
  quando somente um identificador existe. Ambos preenchidos ficam NULL e
  pendentes. `participante_id_origem` Magento fica NULL; a `participante_key`
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
etiqueta ou bruto zero somente na ausência de sinal de grupos.

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

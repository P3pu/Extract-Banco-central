# CORE V1 — regras implementadas

Esta implementação é **código para revisão**. Nenhum SQL CORE foi aplicado ao
`Atendimento` nesta tarefa. O executor CORE é separado do D1/RAW e lê somente
as views STAGING PostgreSQL. A view de indicadores permanece `WHERE FALSE`.

## Grão e identidade

- `fato_pedido`: `(origem, pedido_id_origem)`; protocolo Ativo = ID do pedido,
  Magento = `increment_id`. Cabeçalho financeiro entra uma vez por pedido.
- `fato_inscricao`: `(origem, inscricao_id_origem)`; Ativo = pedido_evento,
  Magento = bundle pai. Filhos não viram inscrições. Órfãs e pedido NULL ficam.
- Participante Ativo é preservado com namespace `Usuario` ou `UsuarioBalcao`
  quando somente um identificador existe. Ambos preenchidos ficam NULL e
  pendentes. Participante Magento fica NULL. Comprador Ativo fica NULL. Não há
  matching de pessoa/CPF nem união de eventos pelo SKU.

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
  kit = `vl_kit` da categoria; líquido = `GREATEST(0,preco-desconto-kit)`
  somente com todos componentes válidos. Taxa = `nr_taxa` individual,
  segregada do kit e da receita. `preco+taxa` é derivado, não total recebido.
  Pedido Ativo só consolida quando todas as inscrições estão carregadas, os
  status são interpretáveis e os componentes calculáveis; na perda de
  cobertura, totais voltam a NULL.

## Classificação, eventos e combos

GRUPOS > CORTESIA > SITE. Ativo aceita prefixo GR do cupom e categoria
`grupo`/`Saúde Corporativa`; o campo de classificação do cabeçalho de cupom
não está na STAGING e não é simulado. Cupom sem esse atributo e sem sinal GR
fica com classificação pendente. Magento aceita prefixo GR e etiqueta de
regras; categoria numérica não é tratada como texto. Cortesia usa categoria,
etiqueta ou bruto zero somente na ausência de sinal de grupos.

Eventos nascem separados por `(origem, ID)`. Apenas o evento Ativo 22054 tem
evidência versionada de teste; outros precisam de curadoria. `dim_combo`
recebe ID/nome Ativo, mas composição e quantidade prevista permanecem NULL.
Não há cálculo confiável de combos vendidos/ticket até validação de composição
e atribuição de cada inscrição.

## Reprocessamento e segurança

Ranges têm no máximo 100.000 IDs inclusivos. Eventos, combos e pedidos
reprocessados invalidam inscrições afetadas. Alterações em cadastros auxiliares
(categoria, cupom, regra, filho de bundle) exigem reprocessamento da faixa de
inscrições afetada; a reconciliação deve concluir antes de qualquer abertura
da view. O runner usa lock global, transações, auditoria, hash de dependências
e bloqueio de `Atendimento` sem dois sinais explícitos de aprovação. Nenhuma
rota FULL/MySQL/timer foi adicionada.

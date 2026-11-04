# KPIs de Sales Growth

## Aonde queremos chegar

Responder em segundos, para qualquer evento ou canal: **estamos vendendo mais ou menos do
que antes, e quanto?**

Chegamos lá quando:

1. Cada KPI tem uma única definição, escrita aqui.
2. O mesmo KPI dá o mesmo número em qualquer lugar.
3. Qualquer evento ou canal pode ser filtrado, e sem filtro aparecem os dados gerais.
4. Toda prova com edição anterior é comparada com ela.
5. Os números se atualizam sozinhos, e cada KPI tem uma meta para dizer se o resultado é bom.

## Situação em 04/11/2026

| Objetivo | Situação | O que falta |
|---|---|---|
| Definição única | Feito | Fechar as decisões abaixo |
| Mesmo número em todo lugar | Parcial | Só o painel calcula; o cálculo não está no repositório |
| Filtros de evento e canal | Feito | Nenhuma pessoa conferiu a tela ainda |
| Comparação por edição | Parcial | Cobre 60% dos inscritos de 2026; provas que mudaram de nome ficam de fora |
| Atualização automática | Não feito | O painel é uma foto, atualizada a pedido |
| Metas | Não feito | Definir as metas |

## Definições

**Crescimento** = período atual ÷ período anterior − 1. Sem vendas no período anterior, o
resultado é "Sem base", nunca 0% nem 100%.

| KPI | Pergunta | Período atual | Comparado com |
|---|---|---|---|
| Daily Sales Growth | Vendeu mais que no dia anterior? | Data de referência | Dia anterior |
| Sales Growth WoW | E na semana? | Segunda até a referência | Mesmos dias da semana anterior |
| Rolling 7-Day Growth | Qual é a tendência recente? | Últimos 7 dias | 7 dias antes desses |
| Sales Growth MoM | E no mês? | Dia 1 até a referência | Mesmos dias do mês anterior |
| Sales Growth YoY | E contra o ano passado? | Dia 1 até a referência | Mesmos dias do mês no ano anterior |
| Revenue Growth | O faturamento cresceu? | 1º de janeiro até a referência, em R$ | Mesmo período do ano anterior |
| Sales Volume Growth | A quantidade cresceu? | 1º de janeiro até a referência, em inscrições | Mesmo período do ano anterior |
| Growth by Event | A prova vende mais que a edição anterior? | Vendas da prova até a referência | Edição anterior, na mesma antecedência da prova |
| Growth by Channel | Qual canal puxa o resultado? | Qualquer período acima, por canal | O mesmo período do canal |

Quando a referência é o último dia do mês, MoM e YoY comparam meses inteiros: outubro contra
setembro inteiro, por exemplo. Prova já realizada compara o total das duas edições.

## O que entra no número

| Item | Regra |
|---|---|
| Venda | Inscrição com `contabiliza_inscricao` verdadeiro hoje |
| Data da venda | `fato_pedido.data_pedido`, não a data do pagamento |
| Faturamento | `valor_bruto_inscricao` com `contabiliza_bruto` verdadeiro |
| Cortesia e grupos | Entram: cortesia soma no volume, e o faturamento dela é o valor que tiver |
| Cancelamentos | Saem do histórico, então períodos passados podem mudar |
| Referência padrão | Último dia completo, porque o dia atual ainda está em andamento |
| Período coberto | Pedidos de 2023 em diante |

Base dos cálculos, só com agregados:

```sql
SELECT p.data_pedido::date AS dia,
       COALESCE(f.evento_key, 0) AS evento_key,
       f.origem,
       COUNT(*) AS inscritos,
       ROUND(COALESCE(SUM(f.valor_bruto_inscricao) FILTER (WHERE f.contabiliza_bruto), 0), 2) AS bruto
FROM core.fato_inscricao f
JOIN core.fato_pedido p ON p.origem = f.origem AND p.pedido_id_origem = f.pedido_id_origem
WHERE f.contabiliza_inscricao AND p.data_pedido >= '2023-01-01'
GROUP BY 1, 2, 3;
```

## Como ler

- **Comece pelo Rolling 7-Day.** É o que menos oscila com dia da semana.
- **Daily e WoW mudam muito.** Feriados e aberturas de lote pesam, e no início da semana
  ou do mês o período tem poucos dias.
- **Evento de ano fixo não tem YoY.** Filtrando só 2026, o ano anterior fica sem vendas. Para
  comparar uma prova com o ano passado, use Growth by Event.

## Decisões em aberto

| Decisão | Hoje | Por que importa |
|---|---|---|
| Metas de cada KPI | Nenhuma | Sem meta, o número não diz se o resultado é bom |
| Cortesia conta no crescimento? | Conta | Cortesia aumenta o volume sem aumentar a receita |
| Data da venda | Pedido | Pela data do pagamento, os números mudam de dia |
| Faturamento bruto ou líquido | Bruto | O líquido do Magento ainda não é confiável (item 6 das [pendências](CORE_PENDENCIAS.md)) |
| Nomes de provas que mudaram | Sem lista | Uma lista confirmada aumenta a cobertura por edição |

## Próximos passos

1. Conferir a aba Crescimento na tela e validar as definições acima.
2. Fechar as decisões em aberto, começando pelas metas.
3. Levar o cálculo e a ligação entre edições para o repositório, para o número não depender do painel.
4. Confirmar os nomes das principais provas que mudaram.
5. Decidir a API que atualiza o painel sozinho.

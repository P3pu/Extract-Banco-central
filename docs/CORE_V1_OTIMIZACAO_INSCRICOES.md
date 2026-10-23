# CORE V1 — carga histórica de inscrições com cache de sessão

Em 2026-10-23, a estrutura CORE e os pedidos foram carregados no banco
`Atendimento`. O primeiro lote de inscrições (IDs 0–999) foi revertido por
`statement_timeout`; nenhuma inscrição ficou gravada. `EXPLAIN` sem
`ANALYZE` mostrou agregações repetidas sobre milhões de itens Magento em
`030_inscricao_base.sql`, `041_inscricao_magento.sql` e
`050_reconciliacao_pedidos.sql`.

No piloto após a otimização, o item bundle Magento de ID `0` revelou outra
incompatibilidade: o fato aceitava zero, mas o alerta de qualidade exigia ID
positivo. A migração `007_core_alerta_zero_id.sql` altera apenas essa
restrição CORE para `>= 0`. O lote falho foi revertido e auditado antes da
correção; nenhum ID é renumerado ou descartado.

O comando `bulk-inscriptions` materializa uma vez, na própria sessão, somente
os campos necessários das views STAGING Magento e os IDs de pedido das
inscrições Ativo. Cria índices e estatísticas **temporários** para as buscas
por inscrição/pedido. Os SQL de negócio são os mesmos, com referências às
projeções temporárias durante essa execução. Nenhuma tabela ou view RAW/STAGING
é modificada. O cache desaparece quando a conexão fecha.

O primeiro lote real de 100.000 IDs excedeu 60 segundos e foi revertido. Uma
medição de 10.000 IDs terminou em 45 segundos; a reconciliação de pedidos
consumia quase todo o tempo. Por isso o cache Ativo passou a guardar a
contagem por `id_pedido`, calculada uma única vez da RAW (grão 1:1 da view
`staging.ativo_inscricao`). O CTE de cobertura em `050` lê essa contagem
pré-agregada; todas as demais regras financeiras foram mantidas. O tamanho
seguro do lote ainda precisa ser medido no banco real antes da sequência.

Uma segunda medição de 10.000 IDs mostrou que a consulta Magento e a
reconciliação ainda repetiam somas de filhos/bundles por pedido, terminando
esta última em timeout. O cache agora pré-agrega componentes por bundle e
descontos/brutos por pedido uma vez por sessão. Os dois CTEs consumidores
consultam esses resumos; as expressões de soma, precedência de desconto e
validação de quantidade permanecem equivalentes às originais. A equivalência
de valores é testada em fixtures sintéticas antes da medição real.

A medição por etapa no Atendimento mostrou aumento não linear dos custos de
derivação Magento e reconciliação conforme a faixa cresce. A junção com o
bundle pai agora repete explicitamente o limite da chave de inscrição, e a
reconciliação seleciona pedidos Ativo/Magento por ramos separados para usar
o índice existente `(origem, inscricao_id_origem)`. Nenhuma regra financeira
foi alterada. O tamanho de lote continua condicionado à medição real e aos
limites de CPU, memória e tempo do servidor.

O plano real da reconciliação revelou estimativa de apenas um pedido para
uma faixa que acabara de ser inserida na mesma transação. Isso levava a
junções aninhadas quadráticas sobre milhares de pedidos. Antes do SQL de
reconciliação, o executor agora preenche e analisa uma tabela **temporária de
sessão** com os pedidos da faixa. O CTE `pedidos` usa essa tabela, sem DDL
permanente. No Atendimento, a faixa Ativo 8.006.000–8.025.999, que antes
atingia 60 s e era revertida, concluiu em 16,6 s; a consulta de
reconciliação levou 10,8 s. Este resultado não autoriza presumir o mesmo
tempo para todas as faixas; pilotos mistos e monitoramento contínuo são
necessários.

A faixa mista Ativo/Magento 44.000–63.999 concluiu em 33,4 s, com 22,1 s
na derivação Magento e 5,6 s na reconciliação. A escolha inicial para carga
contínua é de no máximo 10.000 IDs nas faixas mistas e 20.000 nas faixas
somente Ativo; qualquer timeout ou divergência exige interrupção e revisão
da faixa. A seleção de pedidos temporária é reconstruída e analisada em
cada transação, impedindo o uso de estimativas defasadas para linhas recém-
inseridas.

A derivação Magento também recebia estimativa defasada para inscrições
inseridas na mesma transação. Uma projeção temporária e analisada do lote
passou a alimentar apenas essa derivação. No Atendimento, a faixa
264.000–273.999 concluiu em 10,9 s, com 1,24 s na derivação Magento, ante
cerca de 20–24 s nas faixas anteriores. Um piloto de 50.000 IDs mistos
(274.000–323.999) atingiu o timeout na reconciliação e foi revertido; esse
tamanho não está aprovado. A carga restante deve usar no máximo 20.000 IDs
por transação, mantendo 60 s por consulta e conferindo origem, contagens,
espaço e gate de indicadores a cada bloco.

## Segurança operacional

- Destino `Atendimento` continua exigindo `--approve-production` e
  `CORE_PRODUCTION_APPROVAL=CORE_V1_APPROVED`.
- Conexões remotas continuam exigindo TLS `verify-full`; `sslmode=disable` é
  admitido apenas em loopback/socket local protegido por túnel SSH validado.
- Cache: `statement_timeout=300000` ms, `lock_timeout=5000` ms, sem limite
  persistente alterado. Depois do cache, cada consulta volta a 60 segundos.
- Lock consultivo global cobre materialização e lotes. O primeiro lote tem
  até 1.000 IDs; os demais, até `--chunk-size` (máximo 100.000 IDs inclusivos).
- Cada lote possui transação e auditoria próprias. Em falha, o lote é
  revertido e marcado `FAILED`; os lotes anteriores permanecem. Reiniciar é
  idempotente, mas reconciliações e validações devem ser repetidas.
- Conferir espaço temporário, atividade e ausência de outra carga RAW antes
  de iniciar. Não aumentar timeouts ou carga concorrente para contornar erro.
- A view `core.fato_inscricao_indicadores_validos` permanece `WHERE FALSE`.

## Homologação local

Em volume Docker novo, as 31 views STAGING compilaram; migrations, eventos,
combos, pedidos e o comando `bulk-inscriptions` executaram com fixtures
sintéticas. A suíte V1/Fase B/C1/C2 passou após a correção de ID zero:
67 testes e 18 subtestes. O upgrade 006→007 foi testado separadamente em
volume local previamente migrado. Foi
verificada equivalência entre derivação com cache e execução original,
idempotência, finanças Magento/Ativo, status, órfãos e ausência de cache
permanente. Volume preservado e container parado.

O laboratório pequeno comprova semântica, não tempo de execução real. Antes
da carga completa, verificar no `Atendimento` os planos das projeções
temporárias, testar o lote-piloto e interromper diante de timeout, pressão de
disco/memória ou divergência de contagem. Não publicar indicadores até
reconciliação histórica e dependências auxiliares aprovadas.

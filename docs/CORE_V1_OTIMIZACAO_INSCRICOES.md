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

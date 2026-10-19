# Revisão dos SQL CORE propostos

Estes arquivos são propostas, **não foram aplicados**. Não executar no banco
`Atendimento` antes de aprovação explícita, homologação e backup. A RAW, a
STAGING e a CORE em produção não foram alteradas nesta revisão.

## Parâmetros no pgAdmin

Os scripts `003`, `004` e `005` usam `core.batch_min()` e `core.batch_max()` em
vez de `:id_min`/`:id_max` (sintaxe específica do `psql`). Após aprovar e criar
`001`/`002` em homologação, abra **uma única sessão** do Query Tool e defina
uma faixa de até 100.000 IDs. Substitua os dois números deste exemplo:

```sql
SELECT set_config('core.id_min', '166000', false),
       set_config('core.id_max', '166999', false);
SELECT core.batch_min(), core.batch_max();
```

Execute um bloco lógico/uma transação de cada vez, na ordem descrita em
`docs/CORE_FASE_B_MODELO.md`. Os filtros por pedido em `004`/`005` mantêm
todos os bundles de um pedido no mesmo lote. **Não** execute a história toda
numa faixa única. O helper falha se parâmetros faltarem, forem inválidos,
invertidos ou cobrirem mais de 100.000 IDs inclusivos (`max - min <= 99999`). Sessões pgAdmin diferentes não
compartilham esses valores; confirme a faixa antes de cada bloco. Ao terminar:

```sql
RESET core.id_min;
RESET core.id_max;
```

`004` contém apenas candidatos de transformação; depende das views opcionais
de `000` e não escreve na CORE. `005` grava somente dados básicos. Se a base
mudar, preserva os indicadores derivados antigos, mas define
`estado_derivacao='PENDENTE'`. O hash básico não abrange todas as dependências
dos indicadores. Por segurança, `core.fato_inscricao_indicadores_validos` está
**fechada por `WHERE FALSE` e retorna zero linhas**. Nenhum job derivado ou
reconciliador de dependências foi implementado. O contrato de fingerprint,
invalidação transacional, versão de regras e reabertura futura do gate está em
`docs/CORE_FASE_B_MODELO.md`. Não usar derivados da tabela base para métricas.

## Alertas e PII

`core.core_alerta_qualidade` aceita apenas PK numérica de origem e código de
regra controlado. Não possui mensagem livre. `core_etl_execucao` aceita apenas
código de erro controlado; logs futuros não devem imprimir exceções de driver,
CPF, nome, e-mail ou parâmetros de conexão. `dim_pessoa` aceita token binário
de 32 bytes, mas a geração HMAC, guarda do segredo e papéis de acesso ainda
precisam de aprovação. As constraints não provam que um número veio da PK da
fonte: o futuro loader deverá validar a proveniência e os grants/logs antes de
inserir qualquer identificador. **Não preencher `dim_pessoa` nesta fase.**

Antes de executar qualquer DML em homologação, explicar o plano de cada lote
com `EXPLAIN` sem `ANALYZE`, testar unicidade dos SELECTs, comparar
`900_core_acceptance_readonly.sql` e registrar contagens antes/depois.

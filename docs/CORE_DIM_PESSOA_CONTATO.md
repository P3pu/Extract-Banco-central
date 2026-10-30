# CORE — contato restrito em `dim_pessoa`

## Estado operacional em 27/10/2026

A migração `008_dim_pessoa_contato.sql` foi aplicada no `Atendimento` pelo
túnel SSH. Após autorização específica, o backfill limitado a 10.000 IDs
desde 26/10/2026 processou 1.421 pedidos e 3.399 inscrições. A solicitação
posterior para começar em 01/01/2026 foi iniciada em lotes diários: 01/01
processou 714 pedidos e 1.259 inscrições; 02/01 processou 1.359 pedidos e
2.657 inscrições. A inspeção posterior encontrou 3.054 pessoas e 3.066 mapas,
com 3.040 CPFs validados, zero tokens duplicados e zero mapas órfãos. Nome e
e-mail estão preenchidos em 3.053 pessoas cada. Os dados pessoais não foram
exportados nem registrados em logs. Em 30/10/2026 a chave foi rotacionada,
o backfill desde 01/01/2026 foi executado no servidor e o gate
`CORE_PII_ENABLE_SYNC` passou a ficar aberto no `bcd-raw-core.service`.

O `EXPLAIN` sem `ANALYZE` para o período desde 01/01 estimou cerca de 610 mil
pedidos e 901 mil inscrições. O processamento contínuo dos demais dias requer
uma janela operacional e autorização específica para o volume e a duração;
nenhuma rotina persistente de backfill foi criada ou ativada. Compradores
Ativo e associações Magento ambíguas/ausentes não são inferidos nem mesclados
por nome/e-mail.

## Escopo

A migração `sql/core/v1/008_dim_pessoa_contato.sql` acrescenta `cpf`, `nome` e
`email` à `core.dim_pessoa`. São dados pessoais em texto, restritos ao dono da
tabela e a acessos explicitamente revisados. Os fatos não repetem esses campos:
`comprador_key` e `participante_key` apontam para a dimensão. A migração não
altera RAW/STAGING, não abre `core.fato_inscricao_indicadores_validos` e não
cria MART.

O sincronizador usa somente vínculos comprovados:

- Magento: `fato_pedido.comprador_id_origem` → `staging.magento_cliente`;
  participante de bundle com associação não ambígua → mesmo cadastro.
- Ativo: `fato_inscricao.participante_id_origem` e seu namespace `Usuario` ou
  `UsuarioBalcao` → respectivo cadastro STAGING.
- Ativo comprador: `fato_pedido.comprador_id_origem` (`sa_pedido.id_usuario`,
  desde 30/10/2026) → `staging.ativo_usuario`, namespace `Usuario`. Nunca usa
  o participante como comprador. A mesma pessoa (mesmo CPF) que compra para si
  e aparece em pedidos de outros compradores fica com papel `AMBOS`.

O sincronizador verifica os dígitos do CPF. Para CPF válido, calcula HMAC-SHA256
com segredo externo e usa o índice único de `cpf_token_seguro` para reutilizar
uma única `pessoa_key` entre comprador e participante, inclusive entre Magento
e Ativo. Cada ID de origem fica registrado em `core.pessoa_source_map`; os
fatos apontam para a mesma dimensão. CPF ausente ou inválido permanece por ID
de origem (`SOURCE_ID`), sem junção por nome ou e-mail. O CPF de origem é
preservado no campo `cpf`; `cpf_valido` informa o resultado da validação.
Um CPF válido repetido pode não representar a mesma pessoa em cadastros
incorretos: conflitos de CPF de um ID já mapeado ou mapeamentos antigos que
exigiriam mesclar duas `pessoa_key` interrompem a carga para revisão, sem
mesclagem destrutiva automática. A consulta de exportação agrupa por
`pessoa_key`, refletindo apenas as identidades efetivamente consolidadas.

Antes de aplicar a migração, provisionar a chave padrão em
`%LOCALAPPDATA%\BancoCentralDados\core-person-hmac.key`, ou apontar
`CORE_PII_HMAC_KEY_FILE` para outro arquivo fora do repositório. O conteúdo
deve ter pelo menos 32 bytes aleatórios representados por 64 ou mais
caracteres hexadecimais, acessíveis somente ao usuário da automação.
Manter o mesmo segredo em todas as execuções; rotação exige procedimento
próprio para recalcular os tokens. Sem a chave, a sincronização de CPFs válidos
falha antes de gravar dados ou avançar o diário de alterações. Não registrar
o segredo em Git, argumentos de linha de comando ou logs.

## Rotação da chave (30/10/2026)

A chave usada no backfill de 27/10 não foi localizada. Decisão: gerar uma
chave nova e recalcular os tokens a partir do CPF guardado na `dim_pessoa`
(3.040 CPFs validados, todos recalculáveis, sem repetição). `pessoa_key`,
`pessoa_source_map` e os fatos não mudam. No servidor a chave fica em
`/var/lib/bcd/core-person-hmac.key` (`BCD_STATE_DIR`), dono `bcd`, modo 0400,
fora da release. Gerar sem exibir o conteúdo:

```bash
sudo -u bcd sh -c 'umask 077; test ! -e /var/lib/bcd/core-person-hmac.key &&
  python3 -c "import secrets;print(secrets.token_hex(32))" > /var/lib/bcd/core-person-hmac.key &&
  chmod 0400 /var/lib/bcd/core-person-hmac.key'
```

Depois, com a automação parada e `CORE_PII_APPROVAL=DIM_PESSOA_PII_APPROVED`:
`python -m src.core.person_dimension rotate-key --approve-production`. A rotação
é uma transação única e confere o resultado antes do COMMIT. Guardar uma cópia
da chave em cofre: sem ela, nova rotação será necessária. A sincronização
compara a chave com os tokens gravados e recusa chave divergente
(`Chave HMAC diverge dos tokens gravados`), evitando pessoas duplicadas.

## Aplicação controlada

A migração **não é aplicada automaticamente** pela RAW ou pelo agendamento.
O preenchimento também fica fechado por padrão, inclusive no agendamento:
`CORE_PII_ENABLE_SYNC=approved` só deve ser definido após aprovação explícita
do volume e da política de acesso. A existência das colunas não ativa cargas.
O comando só aceita o banco `Atendimento` via túnel SSH dedicado e exige
`--approve-production` e `CORE_PII_APPROVAL=DIM_PESSOA_PII_APPROVED` no ambiente
do processo. Nunca colocar a senha ou esse gate em Git, logs ou argumento.
Antes de aplicar, a rotina verifica a ausência de `SELECT` explícito a outros
papéis na `dim_pessoa`; privilégios globais como `pg_read_all_data` exigem
revisão administrativa separada. Não revoga grants de terceiros sozinha.

Com o túnel novamente disponível e após revisão do ACL/backup, executar em
PowerShell a partir da raiz do projeto:

```powershell
$env:CORE_PII_APPROVAL = 'DIM_PESSOA_PII_APPROVED'
.\.venv\Scripts\python.exe -m src.core.person_dimension inspect
.\.venv\Scripts\python.exe -m src.core.person_dimension migrate --approve-production
$env:CORE_PII_ENABLE_SYNC = 'approved' # apenas apos aprovar o volume
.\.venv\Scripts\python.exe -m src.core.person_dimension backfill --since 2026-10-26 --max-ids 1000 --approve-production
Remove-Item Env:CORE_PII_APPROVAL
Remove-Item Env:CORE_PII_ENABLE_SYNC
```

O backfill acima limita pedidos e inscrições a 1.000 IDs cada e considera a
data do pedido. Inscrições novas vinculadas a pedidos anteriores, cadastros
históricos e mudanças cadastrais sem alteração RAW do pedido/inscrição exigem
uma reconciliação adicional aprovada; não se presume cobertura total. Cada
ciclo automatizado subsequente sincroniza somente os IDs RAW alterados se o
gate estiver aprovado no ambiente da tarefa. Sem o gate, a RAW/CORE existente
segue sem o novo passo.

## Verificação sem expor dados pessoais

Depois do backfill, verificar contagens e vínculos, sem imprimir CPF/nome/email:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SELECT COUNT(*) AS pessoas_com_contato
FROM core.dim_pessoa
WHERE cpf IS NOT NULL OR nome IS NOT NULL OR email IS NOT NULL;
SELECT origem, tipo_identificador, COUNT(*) AS ids_mapeados
FROM core.pessoa_source_map
GROUP BY origem, tipo_identificador
ORDER BY origem, tipo_identificador;
SELECT origem, COUNT(*) FILTER (WHERE comprador_key IS NOT NULL) AS compradores_vinculados
FROM core.fato_pedido GROUP BY origem;
SELECT origem, COUNT(*) FILTER (WHERE participante_key IS NOT NULL) AS participantes_vinculados
FROM core.fato_inscricao GROUP BY origem;
COMMIT;
```

Para a lista de hoje (somente CORE), usar
`sql/core/v1/920_pessoas_hoje_readonly.sql`. A exportação contém PII e deve ser
guardada e enviada apenas por canal autorizado; não anexar CSV ao repositório.

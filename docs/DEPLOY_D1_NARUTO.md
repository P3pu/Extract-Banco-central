# Deploy D1 — preparação, sem ativação

**Estado:** proposta derivada de `review/raw-index-r1-magento` (`752b40c`).
O diagnóstico D2 de 21/10/2026 foi concluído por SSH autenticado e somente
leitura, com validação da chave do servidor. O inventário e os bloqueios estão
em [DEPLOY_D2_NARUTO_DIAGNOSTICO.md](DEPLOY_D2_NARUTO_DIAGNOSTICO.md).
Não houve consulta SQL, build/execução de container, carga nem alteração no
servidor. Endereço, fingerprint e credenciais não são versionados.

## Roteiro para repetir o diagnóstico remoto

Com acesso por canal seguro, conferir novamente a fingerprint antes de aceitar
a chave, mantendo `StrictHostKeyChecking=ask` ou `yes` (nunca `no`). Preferir
conta de diagnóstico sem privilégio; `root` foi apenas o acesso inicial
disponível. Executar `sh deploy/d1/diagnose-readonly.sh` ou os comandos abaixo,
individualmente, sem salvar saída bruta no repositório:

Na estação Windows, se for necessário iniciar uma sessão manual, obter o IP
do inventário confiável e informar a credencial apenas no prompt SSH; não
passá-la como argumento:

```powershell
$narutoIp = Read-Host 'IP do Naruto (inventário confiável)'
ssh -p 22 -o StrictHostKeyChecking=ask root@$narutoIp
```

Comparar a fingerprint exibida com a referência recebida por canal separado
**antes** de responder ao prompt. Se for diferente, cancelar; não usar
`StrictHostKeyChecking=no` ou `ssh-keyscan` como fonte de confiança.

```bash
whoami
hostname
uname -a
cat /etc/os-release
nproc
docker --version
docker compose version
git --version
python3 --version
df -h
df -i
free -h
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
systemctl is-active postgresql
```

O inventário básico confirmou Linux, CPU, RAM, disco, containers e PostgreSQL
em Docker Swarm. A rede overlay do banco não aceita containers comuns; a rota
do futuro executor pelo endpoint publicado, o DNS, o TLS e o acesso às origens
MySQL continuam **NÃO VERIFICADOS**. Não despejar `env`, inspeção de variáveis
de containers, arquivos de segredo ou dados de negócio.

## Arquitetura proposta, desligada por padrão

`deploy/d1/compose.yaml` define **somente** executor Python em projeto/rede
próprios, sem portas publicadas e sem volume PostgreSQL. Roda como UID/GID
10001, filesystem raiz somente leitura, capacidades removidas e segredos em
montagem read-only. O perfil `manual` evita início implícito. `serve` fica
ocioso e grava heartbeat em tmpfs; o healthcheck mede **somente liveness**,
não sucesso da ETL, conexão ou atualidade da RAW. `restart: unless-stopped`
recupera o serviço ocioso após falha/reboot, sem agendar cargas sozinho.

As unidades/timers systemd são **modelos não instalados**. Cadência proposta:
Magento na hora cheia, Ativo no minuto 30, ainda sujeita a dimensionamento.
O script `run_incrementals.sh` usa `flock` global no host, executa entidades
sequencialmente e preserva os advisory locks PostgreSQL por entidade. Lock
ocupado retorna 75 e precisa de alerta, não é sucesso. Falha de entidade
interrompe o grupo. Logs JSON do Python vão ao journal; `raw._etl_runs` e
`raw._etl_watermark` registram resultado, mas não há ainda canal externo de
alerta nem política de retenção do journal. Não ativar timer sem isso.

O wrapper não aceita `FULL`, `SNAPSHOT`, `RECONCILIATION` nem execução sem
entidade. `incremental` exige `D1_ENABLE_INCREMENTALS=approved`; o exemplo
vem com `no`. Primeira onda proposta: Magento `sales_order` e
`sales_order_item`; Ativo `pedido` e `pedido_evento`. **Não cobre toda a RAW**.
Outras entidades entram apenas após revisão de dependências, custo e
reconciliação. CORE/MART e índice RAW R1 ficam fora deste deploy.

## Continuidade e risco do primeiro incremental

O contrato versionado de `raw._etl_watermark` usa PK `(pipeline_name,
source_system, source_table)` e campos de estratégia, coluna, valor e
`last_success_at`; valores reais não foram consultados. O último watermark
informado é de 28/09/2026. Antes da primeira carga: verificar em leitura que
cada entidade agendada tem watermark e run `SUCCESS`; estimar backlog, espaço
e duração; executar uma entidade por vez sob observação. Watermark ausente
faz o código exigir FULL; **não** executar FULL nem inventar watermark.
Habilitar timers somente depois de um primeiro ciclo incremental aprovado,
conferido e com plano de recuperação.

Magento `sales_order` pagina por `updated_at` com sobreposição de cinco
minutos; `sales_order_item` filtra `updated_at` enquanto percorre a PK,
pois não há índice dessa coluna na origem. O backlog pode custar leitura
extensa no MySQL. Ativo usa PK crescente e não captura atualização em ID
antigo sem reconciliação. `postgres_loader.upsert` atualiza por PK; cada job
usa lock de sessão e grava `RUNNING`, `SUCCESS`/`FAILED` e watermark. Rever
timeouts e espaço antes de ativar.

## Reconciliação existente — nenhuma agenda D1

| Origem | Entidades | Cobertura atual |
|---|---|---|
| Ativo | `pedido`, `pedido_evento` | Pedidos recentes; janela padrão 30 dias. |
| Ativo | `usuario`, `usuario_balcao` | Referências em pedidos recentes. |
| Ativo | `pedido_pagamento`, `transacao` | Datas financeiras/de pedido; `transacao` exige seleção explícita. |
| Ativo | `pedido_endereco` | Pedidos recentes. |
| Ativo | `cupom_desconto_item` | Referências; seleção explícita. |
| Ativo | `pedido_produto` | Sem `RECONCILIATION`; `SNAPSHOT` pode remover ausentes e exige aprovação separada. |
| Magento | `sales_order`, `sales_order_item`, `product`, `customer`, `customer_address` | `updated_at` com sobreposição. |
| Magento | demais relações/EAV/regras | Alguns usam PK incremental/snapshot; sem reconciliação histórica geral. |

O `reconcile` sem entidade no CLI omite `transacao` e
`cupom_desconto_item`. Reconciliar a cada 15/30 dias é meta, não agendamento
aprovado. É preciso validar janela, cobertura, custo e cada entidade.

## Segredos e infraestrutura

`.env.example` tem somente parâmetros não secretos. Em produção,
`/etc/bcd-d1/compose.env` (fora do Git) conteria endpoints/usuários, porta
PostgreSQL explícita e gate;
três senhas e CAs ficariam em `/etc/bcd-d1/secrets`, sem senha em argumento
ou no `docker inspect`. O entrypoint lê esses arquivos no processo. Restringir
permissões ao operador e UID/GID do executor. `.dockerignore` exclui `.env`,
segredos, certificados, Git e anexos do contexto de build.

Dependências diretas estão fixadas a partir do ambiente local. A imagem-base
usa Python 3.12/Bookworm por tag; antes de produção, validar wheels Linux,
fixar digest e hashes dos pacotes em homologação. Ainda não é build plenamente
reprodutível. `POSTGRES_SSLMODE=verify-full` e CAs são propostos; conferir
hostname/certificado e topologia real. O executor D1 recusa porta PostgreSQL
`UNSET` e modo diferente de `verify-full`; não enfraquecer TLS para contornar
falha. A rede própria precisa de rota aprovada aos bancos; não modificar o
serviço PostgreSQL existente.

No D2, a conta `bcdsvc` e o checkout proposto não existem; `git` também não
está instalado. O Docker do host não é rootless e seu socket pertence a
`root:docker`; acesso ao daemon equivale a privilégio elevado. Definir antes
uma identidade/mecanismo aprovado. **Não** adicionar `bcdsvc` ao grupo
`docker` automaticamente. O `StateDirectory` systemd armazenaria só o lock
global.

## Sequência futura — exige autorização separada

1. Revisar o diagnóstico D2 e resolver recursos, rota, TLS e identidade de
   serviço pendentes. Conferir watermarks/runs somente após autorização de
   leitura separada e dimensionar backlog.
2. Homologar build Linux; fixar digest/hashes; provisionar fora do Git
   `compose.env`, segredos e CAs com permissões restritas.
3. Aprovar entrega do commit como artefato imutável ou instalação controlada
   de Git, que não existe no host, e preparar checkout em
   `/opt/extract-banco-central`.
   Comandos **propostos, não executar agora**:

```bash
docker compose --env-file /etc/bcd-d1/compose.env -f /opt/extract-banco-central/deploy/d1/compose.yaml --profile manual config
docker compose --env-file /etc/bcd-d1/compose.env -f /opt/extract-banco-central/deploy/d1/compose.yaml --profile manual build executor
docker compose --env-file /etc/bcd-d1/compose.env -f /opt/extract-banco-central/deploy/d1/compose.yaml --profile manual up -d executor
docker compose --env-file /etc/bcd-d1/compose.env -f /opt/extract-banco-central/deploy/d1/compose.yaml --profile manual ps
```

4. Após autorização de carga, alterar gate apenas na configuração aprovada,
   recriar executor e testar cada entidade incremental separadamente; não
   executar `full` nem grupo inteiro sem medir backlog. Instalar/ativar
   unidades e timers só após ciclo observado e agenda/alertas aprovados.
   O script aceita, por exemplo, `sh deploy/d1/run_incrementals.sh magento sales_order`
   para **uma** entidade; sem o segundo argumento executa o grupo proposto.

## Reversão futura — não autorizada

Desabilitar timers primeiro; aguardar/finalizar apenas job D1 identificado,
sem afetar cargas alheias. Retornar gate a `no` e recriar executor, se
necessário. Preservar runs, watermarks e logs. Parar apenas o executor D1,
sem `down --volumes`, sem reiniciar PostgreSQL e sem reverter RAW/DDL. Segredos
são geridos fora do Git e rotação/remoção exige procedimento próprio.

**Gates de aceite:** diagnóstico real; recursos/serviços críticos/rota/TLS;
conta de serviço; build Linux reproduzível; watermarks e backlog; primeiro
incremental observado; monitoramento e cadência aprovados. Até lá, Compose
e timers ficam não instalados e gate `no`.

Referências de segurança: [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/),
[segurança do daemon Docker](https://docs.docker.com/engine/security/),
[Docker rootless](https://docs.docker.com/engine/security/rootless/).

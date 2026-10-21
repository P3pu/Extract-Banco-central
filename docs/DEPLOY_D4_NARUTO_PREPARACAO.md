# D4 — preparação do deploy RAW no worker Naruto

Estado: **somente revisão local**. Nenhum comando deste roteiro foi executado no Naruto nesta fase. A branch D4 parte do commit D3 `3d45918`; substituir `<COMMIT_D4>` pelo SHA completo publicado após revisão. Não criar CORE/MART, índices, serviços Swarm, containers ou cargas durante a preparação.

## Correções D4 e limite da reconciliação

`probe --source postgres|magento|ativo` valida e lê apenas a configuração, a CA e a senha da fonte escolhida. A biblioteca de cada fonte efetua DNS/TCP, autenticação e verificação TLS durante `src.main check`, que não consulta dados de negócio. A sonda MySQL não abre conexão PostgreSQL. `incremental` e `reconcile` continuam exigindo PostgreSQL **e** a origem correspondente; `FULL` não existe no executor. Os dois gates permanecem `no` por padrão.

O timer mensal continua proposto para o dia 1 às 03:00, **não instalado nem ativado**. A janela D4 é fixada em 35 dias no executor e no Compose; outra duração falha antes de conectar. Entre disparos mensais pontuais há 28, 29, 30 ou 31 dias, portanto há no mínimo quatro dias de sobreposição. O corte real vem de `DATE_SUB(NOW(), INTERVAL 35 DAY)` no MySQL Ativo; os filtros de `pedido` e `pedido_evento` usam `dt_pedido` do pedido. A janela **não** garante captar alterações de pedidos cuja `dt_pedido` seja anterior ao corte, independentemente de `updated_at`. Disparo atrasado ou perdido por mais de quatro dias pode romper a cobertura; `Persistent=false` evita catch-up automático. Nesse caso, parar e planejar uma reconciliação manual limitada, com análise de custo e autorização separada — nunca ampliar automaticamente para todo o histórico.

`run_reconciliation.sh` permanece separado de `run_incrementals.sh`. Ambos usam o mesmo `flock` host em `/var/lib/bcd-d1/global.lock`; o PostgreSQL mantém advisory locks por entidade. Comandos `docker compose exec` diretos contornam o lock host e não fazem parte do procedimento de carga.

## Artefato versionado sem Git no Naruto

Preparação em estação confiável **após commit e revisão**:

1. Conferir `git rev-parse HEAD`, árvore limpa e branch D4. Criar um arquivo de fonte **do SHA exato** com `git archive --format=tar.gz --output=bcd-raw-<COMMIT_D4>.tar.gz <COMMIT_D4>`. Não incluir `.env`, certificados, senhas, dados de clientes ou `.git`.
2. Construir e testar imagem Linux `linux/amd64` localmente a partir do arquivo extraído, não de mudanças não commitadas. Usar a tag `banco-central-executor:<COMMIT_D4>`; conferir dependências instaladas de `requirements.lock`, `python -m deploy.d1.entrypoint --help` e UID `10001`. Registrar ID/digest da imagem e resultado dos testes. A base Python por tag e dependências sem hashes ainda limitam a reprodutibilidade; pinagem de digest/hashes e revisão de vulnerabilidades são critérios antes do deploy, não uma garantia desta D4.
3. Exportar a imagem aprovada via `docker save` para `bcd-image-<COMMIT_D4>.tar`. Gerar SHA-256 **de ambos os arquivos**; registrar SHA do commit, checksums e ID da imagem em manifesto assinado/aprovado fora do Git. Transferir fonte, imagem e manifesto pelo canal administrativo aprovado, com host key SSH verificada. Não transferir segredos no pacote.
4. Após autorização futura, conferir no Naruto `sha256sum -c` contra o manifesto recebido por canal confiável; inspecionar `tar -tzf` contra caminhos absolutos, `..` e links inesperados antes de extrair em diretório de release novo, root-owned. `docker load` deve importar somente a imagem com tag do SHA aprovado. `docker image inspect` e `docker compose config` precisam mostrar a mesma revisão. Sem Git instalado no Naruto, essa cadeia (commit de origem + checksum + tag/label + manifesto) identifica o artefato implantado.

Não usar tag mutável como `latest`. `D1_COMMIT_SHA` no `compose.env` futuro deve ser o SHA completo aprovado, nunca `unreleased`.

## Checklist de segurança antes de qualquer criação no worker

- [ ] Aprovação explícita da janela de implantação, conta administrativa e transferência do artefato; nenhuma instalação de pacote/usuário nesta D4.
- [ ] Diretório da release e scripts root-owned, não graváveis por operador não administrador. `compose.env` fora do Git, root-owned `0600`, sem senha; `D1_ENABLE_INCREMENTALS=no` e `D1_ENABLE_RECONCILIATION=no`.
- [ ] Senhas e CAs fora da imagem e do Git em arquivos regulares sem symlink. Diretório de segredos `root:10001` `0750`, arquivos `root:10001` `0640`, após validar que o GID numérico não pertence a outra conta local. O container roda UID/GID `10001` e só recebe montagem read-only de segredos.
- [ ] `docker compose config` mostra apenas serviço executor, rede bridge local, nenhuma porta publicada, nenhum volume PostgreSQL/PGDATA e nenhum `/var/run/docker.sock`; `cpus=0.5`, `mem_limit=768m`, `pids_limit=128`, rootfs read-only.
- [ ] DNS, porta, firewall, CA e SAN/hostname do endpoint PostgreSQL confirmados. `POSTGRES_SSLMODE=verify-full`; não usar IP como atalho nem relaxar TLS. Equivalente para Magento e Ativo com CA MySQL e validação de hostname.
- [ ] Nenhum operador ou conta de serviço no grupo `docker`. As unidades systemd propostas são root-owned, chamam runners fixos e são endurecidas, mas o daemon Docker rootful continua equivalente a privilégio administrativo; aprovação de segurança específica é necessária.
- [ ] Volume e serviço PostgreSQL existentes intocados. Há espaço para imagem e logs; avaliar uso de CPU/RAM e backlog antes de liberar cargas.
- [ ] Timers continuam não instalados/inativos; `Persistent=false`; lock host compartilhado verificado; plano para falha ou timer perdido aprovado.

## Sequência futura de rede/TLS — **não executar nesta fase**

1. Validar checksums/commit, permissões, configuração e imagem. Rodar `docker compose --env-file /etc/bcd-d1/compose.env -f /opt/extract-banco-central/deploy/d1/compose.yaml --profile manual config --quiet`; inspecionar a configuração normalizada sem imprimir valores de segredos.
2. Ainda sem container, confirmar DNS/porta/CA/hostname de cada destino a partir da política de rede e certificados aprovada. Não imprimir conteúdo de CAs ou senhas. A sonda efetiva de rede **a partir do bridge** exige o container e autorização adicional.
3. Após autorização específica, iniciar **apenas** o executor ocioso com a imagem importada, sem build e com gates `no`. Confirmar `docker compose ps` e ID/tag da imagem; nenhuma carga é disparada por `serve`.
4. Dentro do executor, testar DNS/TCP para PostgreSQL, Magento e Ativo separadamente com `socket.getaddrinfo` e `socket.create_connection` usando os hosts/portas do ambiente, sem exibir endereços resolvidos nem executar SQL de negócio. O comando detalhado está em [D3](DEPLOY_D3_WORKER_COMPOSE.md).
5. Executar individualmente, por `docker compose ... exec -T executor python -m deploy.d1.entrypoint`, `probe --source postgres`, depois `probe --source magento`, depois `probe --source ativo`. Cada retorno deve ser zero. As verificações TLS/certificado ocorrem durante a conexão; falha é bloqueante, não motivo para reduzir `verify-full` ou trocar CA.
6. Registrar data, fonte, sucesso/falha, categoria do erro e versão de artefato, **sem** senha, CPF, nomes, e-mail, certificado, endereço resolvido ou valores de negócio. Parar e solicitar **nova autorização** antes de alterar qualquer gate ou executar incremental.

## Rollback futuro sem perda de dados

Se a verificação pré-carga falhar, manter gates `no`, parar apenas o executor D4 autorizado e voltar o ponteiro de release para o artefato anterior aprovado. Não usar `docker compose down --volumes`, não apagar imagens/volumes/segredos e não tocar PostgreSQL ou Swarm. Se houver falha depois de uma carga futuramente autorizada, desativar timers, impedir novas execuções, preservar container/logs e watermarks, registrar último lote e avaliar idempotência antes de retomar; **rollback de código não reverte dados**. A reconciliação atrasada exige plano manual aprovado.

## Critérios para próxima autorização

Testes estáticos D1/D3/D4, `docker compose config`, build/smoke Linux local, revisão de segredos/diff e checksums do artefato devem passar. Ainda serão pendentes a rota real do bridge, SAN/CA, privilégios das contas, custo da reconciliação e aceitação do risco Docker rootful. Nenhuma dessas pendências deve ser tratada como aprovada por testes sintéticos.

## Relatório de testes locais — 21/10/2026

| Verificação | Resultado | Limite |
| --- | --- | --- |
| `python -m unittest tests.test_deploy_d1_static tests.test_deploy_d3_worker_static tests.test_deploy_d4_static` | 18 testes aprovados | Mocks e dados sintéticos; sem conexão real |
| `docker compose ... config --quiet` e inspeção JSON | Aprovado: bridge, sem portas, único mount de segredos, 0,5 CPU, 768 MiB, gates `no`, janela 35 | Não cria container nem comprova rede |
| Build local `linux/amd64` do Dockerfile D1 | Aprovado no Docker Desktop local | Não é build no Naruto nem artefato final do commit |
| Smoke local sem rede: `--help`, UID e imports | Aprovado: sem rota FULL, UID `10001`, `LINUX_IMPORTS_OK` | Não testa TLS/credenciais reais |
| Revisão de diff e busca de segredos | Aprovado: somente arquivos D4 relacionados; sem credenciais, dados pessoais ou endpoints reais. O único IP reconhecido é loopback sintético em teste | Não substitui revisão humana |

Não há suíte D2 independente versionada; os testes D1 e D3 incluem as invariantes observadas no diagnóstico D2. Nenhum volume/serviço de produção foi acessado.

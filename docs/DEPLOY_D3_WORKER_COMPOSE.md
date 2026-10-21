# D3 — executor RAW via Docker Compose local no worker

Status: **preparado para revisão, não implantado**. Esta decisão substitui a proposta de Docker Stack/manager. O diagnóstico D2 identificou Docker Engine/Compose e systemd no worker, mas não comprovou um endpoint PostgreSQL utilizável a partir de um container bridge nem a conectividade TLS com as duas origens MySQL. Nenhuma carga ou criação de container no Naruto faz parte desta etapa.

## Arquitetura e limites

- Reutilizar `deploy/d1/Dockerfile`, `deploy/d1/compose.yaml` e `deploy/d1/run_incrementals.sh`; projeto Compose independente, serviço `executor` sem portas publicadas, rede **bridge local** `source_egress`. Não conectar à overlay Swarm não-attachable e não montar PGDATA, volumes do PostgreSQL ou socket Docker no container.
- Executor UID/GID `10001`, sistema de arquivos somente leitura, capabilities removidas, `no-new-privileges`. Limites iniciais: `0.50` CPU, 768 MiB de RAM, reserva de 256 MiB e 128 processos; rever com métricas antes da primeira sincronização.
- PostgreSQL por **hostname DNS acessível do bridge**, porta explícita, CA em arquivo e `POSTGRES_SSLMODE=verify-full`. O certificado precisa cobrir exatamente o hostname configurado. Não substituir hostname por IP nem reduzir a validação TLS para contornar erro. As duas origens MySQL usam host/porta explícitos e a CA fornecida em `MYSQL_SSL_CA`.
- Credenciais e CAs ficam fora do Git e da imagem em `/etc/bcd-d1/secrets`, montadas apenas para leitura em `/run/d1-secrets`; o diretório e os arquivos devem ser legíveis pelo UID/GID `10001` sem acesso global. Modelo a conferir antes da instalação: diretório `root:10001` modo `0750`, arquivos `root:10001` modo `0640`, sem symlinks; `compose.env` root-owned modo `0600`. Confirmar que o GID numérico não concede acesso a outra conta local. Nenhum endpoint real, senha ou certificado é versionado.
- `D1_ENABLE_INCREMENTALS=no` e `D1_ENABLE_RECONCILIATION=no` por padrão. `probe` é a única nova rota operável sem gate de carga. Não há rota FULL. Os timers são apenas modelos versionados, não instalados nem ativados.

## Sequência de validação futura — requer autorização operacional

Pré-condições: revisão/aprovação dos arquivos, endpoint PostgreSQL e DNS definido pela equipe de infraestrutura, CA/hostname validados, contas de banco com privilégios mínimos, imagem construída localmente no Naruto em janela aprovada e executor já iniciado **sem cargas**. Esta seção é procedimento, não autorização para executá-lo agora.

1. Sem iniciar container, validar a configuração a partir de uma cópia protegida do arquivo não secreto: `docker compose --env-file /etc/bcd-d1/compose.env -f /opt/extract-banco-central/deploy/d1/compose.yaml --profile manual config --quiet`. Conferir que o resultado não publica portas, não monta volumes PostgreSQL e usa apenas bridge local. Não anexar `network_swarm_public`.
2. Com o executor ocioso e após autorização específica para criá-lo, conferir resolução DNS e TCP **de dentro dele**, sem exibir o conteúdo dos certificados: `docker compose --env-file /etc/bcd-d1/compose.env -f /opt/extract-banco-central/deploy/d1/compose.yaml --profile manual exec -T executor python -c 'import os,socket; pairs=[("POSTGRES_HOST","POSTGRES_PORT"),("MAGENTO_MYSQL_HOST","MAGENTO_MYSQL_PORT"),("ATIVO_MYSQL_HOST","ATIVO_MYSQL_PORT")]; [(print(key, "DNS_OK", len(socket.getaddrinfo(os.environ[key], int(os.environ[port])))), socket.create_connection((os.environ[key], int(os.environ[port])), timeout=5).close(), print(key, "TCP_OK")) for key,port in pairs]'`. Não registrar endereços resolvidos. Uma falha impede continuar.
3. Em seguida, executar separadamente `python -m deploy.d1.entrypoint probe --source postgres`, `--source magento` e `--source ativo` via `docker compose ... exec -T executor` no mesmo arquivo/projeto. A rota chama somente `src.main check`: autenticação e metadados mínimos, sem dados de negócio ou cargas. PostgreSQL exige `verify-full` e CA; MySQL exige CA e verificação de hostname pela biblioteca TLS. Falhas de certificado/hostname, DNS, porta ou autenticação são bloqueantes; **não** usar `sslmode=disable`, `require`, `verify-ca` ou CA pública substituta por conveniência.
4. Confirmar também o caminho de rede autorizado e a regra de firewall para o hostname/porta PostgreSQL e para os dois MySQL. DNS/TCP não comprovam, isoladamente, permissão de escrita nem compatibilidade de certificado; o `probe` tampouco comprova desempenho de carga.

## Agendamento, concorrência e privilégios

Os arquivos `bcd-d1-magento.timer`, `bcd-d1-ativo.timer` e `bcd-d1-reconciliation.timer` são modelos **inativos**. O último propõe reconciliação mensal de `pedido` e `pedido_evento` do Ativo com janela configurável (`RECONCILIATION_DAYS=30`), sujeito a orçamento de consulta e aprovação. O runner de reconciliação e o incremental usam o mesmo `flock` não bloqueante em `/var/lib/bcd-d1/global.lock`; o `exec` do Compose é serializado por entidade. O lock funciona apenas para execuções que usam esses runners no mesmo host; chamadas Docker diretas contornam-no e são proibidas no procedimento operacional. O advisory lock PostgreSQL da pipeline permanece como segunda proteção por entidade.

O socket Docker do Naruto é rootful: pertencer ao grupo `docker` equivale a controle administrativo do host. Por isso os modelos systemd usam `User=root`, comando fixo, arquivos e configuração root-owned, `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome` e escrita restrita ao diretório de lock; **nenhum operador nem conta de serviço recebe o grupo `docker`**. Isso limita quem pode invocar o daemon, mas não torna o daemon sem privilégios: uma revisão de segurança deve aceitar esse risco residual ou exigir Docker rootless antes da instalação. Não instalar unidades nem criar usuários nesta fase. A posse/permissões finais de `/opt/extract-banco-central`, `/etc/bcd-d1/compose.env`, `/etc/bcd-d1/secrets` e scripts devem ser verificadas antes de qualquer ativação, para impedir alteração por não administradores.

## Continuidade da RAW e aceitação

Os incrementais Magento continuam em `sales_order` e `sales_order_item`, com watermark persistido no PostgreSQL, UPSERT por PK e sobreposição de cinco minutos em `updated_at`. Ativo `pedido` e `pedido_evento` continuam por PK crescente; a reconciliação histórica é rota separada, fechada por gate próprio. A primeira sincronização deve ser manual, uma entidade por vez, com monitoramento dos watermarks, erros, duração, uso de CPU/RAM e impacto no PostgreSQL. Não executar FULL. Antes de ativar timers, exigir: três probes aprovados, certificado/hostname confirmado, conectividade estável, ensaio de idempotência/lock, orçamento da reconciliação, procedimento de parada/reversão e autorização explícita.

### Parada e reversão futuras

Em falha, não liberar gates nem repetir a carga automaticamente. Para execução futura autorizada, parar/desativar os timers (se instalados), manter o container e os watermarks intactos para diagnóstico, e não usar `down --volumes`. Corrigir a causa e retomar por entidade somente após avaliação do último watermark e da idempotência. Nenhuma etapa de reversão apaga dados, volumes ou índices.

## Bloqueios atuais

1. Endpoint DNS/porta PostgreSQL realmente acessível a partir do bridge e CA com SAN correspondente ainda não comprovados.
2. Rotas/firewall, CA e autenticação TLS para Magento e Ativo ainda não comprovados a partir do worker.
3. Permissões root-owned e legibilidade dos segredos pelo UID `10001` ainda não preparadas/verificadas no Naruto.
4. Custo, duração e impacto da reconciliação mensal ainda não medidos; o timer não pode ser ativado apenas com a validação estática.
5. A aprovação de segurança para unidades root-owned que chamam Docker rootful permanece necessária.

Nesta branch, executar somente `python -m unittest tests.test_deploy_d1_static tests.test_deploy_d3_worker_static` e `docker compose -f deploy/d1/compose.yaml --profile manual config --quiet` no ambiente local. Não usar `up`, `exec` ou `run` no Naruto antes da próxima autorização.

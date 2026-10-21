# D2 — diagnóstico somente leitura do Naruto

**Data:** 21/10/2026. **Escopo:** inventário SSH do host e revisão da proposta
D1; nenhuma implantação foi autorizada. A sessão SSH autenticada usou a chave
de host previamente conferida. Os comandos de inventário foram executados
individualmente. Não houve SQL, consulta a dados de clientes, build, criação
de container, instalação, alteração de serviço, carga ou mudança no Naruto.
Endereço, fingerprint, credenciais e endereços privados não constam aqui.

## Inventário observado

| Item | Observação D2 |
|---|---|
| Sistema | Debian GNU/Linux 13.7 (trixie), kernel 6.12, x86_64. |
| CPU e memória | 2 CPUs lógicas; 7,6 GiB RAM, aproximadamente 4,5 GiB disponíveis no momento da coleta; sem swap. |
| Disco principal | 75 GiB totais, 25 GiB usados, 48 GiB livres (34% de uso). Inodes: 6% usados. |
| Docker | Engine 29.1.2; Compose v5.0.0; serviço systemd Docker ativo. Nó Swarm **worker** ativo. |
| Ferramentas do host | systemd 257; Python 3.13.5; `git` ausente. |
| Armazenamento Docker | Imagens: 5,507 GB; volumes locais: 12,4 GB, ambos ativos. Nenhum volume foi removido. |

Os containers em execução foram identificados por nome/imagem, sem inspecionar
variáveis de ambiente ou arquivos de configuração: `postgres:16` (banco),
`redis:7` (cache), Cloudflared (túnel) e Portainer Agent (administração). As
funções são inferidas pelos nomes/imagens e não foram validadas por acesso às
aplicações. Na amostra de recursos, o container PostgreSQL usava cerca de
2,4 GiB de um limite de 4 GiB. A versão **minor** do PostgreSQL não foi
confirmada por SQL nesta etapa.

## Topologia e compatibilidade D1

- `systemctl is-active postgresql` retornou `inactive`; o PostgreSQL em uso
  aparece como tarefa de container Swarm, nas redes `ingress` e
  `network_swarm_public`. O host escuta na porta de PostgreSQL documentada,
  mas a titularidade/rota dessa publicação não pôde ser confirmada com
  `docker service ls`, pois o nó não é manager.
- `network_swarm_public` tem `Attachable=false`. O Compose D1, que cria uma
  rede bridge própria, **não poderá simplesmente ingressar nessa overlay**.
  A alternativa de conectar ao endpoint publicado depende de teste autorizado
  a partir de um container isolado, DNS/certificado compatíveis com
  `verify-full`, firewall e rota. Nada disso foi testado no D2.
- Docker/Compose e systemd existem, então um executor isolado é tecnicamente
  plausível. O Docker não está em modo rootless; o socket é `root:docker` com
  permissão `660`. Conceder acesso ao daemon exige desenho explícito de
  privilégio. Não adicionar uma conta ao grupo `docker` como atalho.
- `/opt` existe, mas o checkout D1 proposto, `/etc/bcd-d1`, `/var/lib/bcd-d1`
  e a conta `bcdsvc` não existem. `git` também não está instalado. Portanto,
  `run_incrementals.sh` e as unidades systemd não estão prontos para execução.
- O `Dockerfile` com Python 3.12/Bookworm em imagem própria não depende do
  Python 3.13 do host. A arquitetura x86_64 é compatível em princípio; build
  Linux, wheels, digest da imagem e hashes das dependências permanecem sem
  homologação. Nenhum build foi feito no Naruto.
- `compose.yaml` não publica portas nem monta volumes do PostgreSQL, mantém
  perfil manual, UID 10001, raiz somente leitura e gate de incrementais
  fechado. O uso de bridge própria preserva isolamento local, mas ainda
  precisa provar saída para PostgreSQL e os dois MySQL de origem.
- `entrypoint.py` e `.env.example` foram ajustados nesta branch para exigir
  porta PostgreSQL explícita e `verify-full`; a porta padrão não descreve a
  publicação observada. O arquivo de exemplo continua sem credenciais.

## Pendências classificadas

| Prioridade | Pendência | Condição para avançar |
|---|---|---|
| Bloqueante | Rede do executor até PostgreSQL e MySQL; DNS e TLS não verificados. | Teste controlado, sem carga, em ambiente autorizado; confirmar CA, hostname e porta sem reduzir TLS. |
| Bloqueante | Identidade para operar Docker rootful e serviço systemd não definida; `bcdsvc` ausente. | Aprovar mecanismo de menor privilégio e provisionamento separado. |
| Bloqueante | Checkout/artefato não presente e `git` ausente. | Aprovar distribuição imutável do commit ou instalação controlada, em outra etapa. |
| Bloqueante para carga | Watermarks, backlog e espaço/duração do primeiro incremental não aferidos. | Autorizar diagnóstico SQL de leitura em etapa separada e dimensionar execução por entidade. |
| Não bloqueante para revisão | Host tem 2 CPUs, sem swap; PostgreSQL já usa memória relevante. | Definir limites CPU/RAM do executor, concorrência e janela observada antes de build/carga. |
| Não bloqueante para revisão | Imagem/dependências ainda sem digest/hashes e sem build Linux homologado. | Fixar e testar artefato reproduzível fora de produção. |
| Não bloqueante para revisão | Alertas externos/retenção de logs não definidos. | Aprovar observabilidade antes de ativar timers. |

**Conclusão:** o host tem Docker, Compose, systemd e espaço aparente para
avaliar um executor pequeno, mas a infraestrutura **não está pronta para
ativação da RAW incremental**. A topologia Swarm, acesso ao daemon,
distribuição do código e rota/TLS são bloqueios concretos. O espaço livre não
substitui o dimensionamento do backlog. A view de indicadores CORE e os
volumes existentes permaneceram intocados.

## Próxima sequência proposta — nenhuma ação autorizada aqui

1. Revisar este diagnóstico e aprovar o método de entrega do artefato e a
   identidade de serviço sem privilégios excessivos.
2. Planejar teste de rede/TLS a partir de executor descartável e isolado,
   sem cargas nem alteração nos serviços existentes; aprovar antes de executar.
3. Após autorização separada, consultar somente metadados de watermarks/runs
   e dimensionar backlog, CPU, memória, disco e janela da primeira entidade.
4. Homologar imagem Linux reproduzível fora do Naruto; manter gate fechado.
5. Em etapa futura aprovada, instalar o executor, validar saúde/rota e só então
   propor um incremental supervisionado por entidade. Timers vêm por último.

Não fazer merge na `main`, instalar componentes, modificar Swarm/PostgreSQL,
executar cargas ou ativar timers com base apenas neste diagnóstico.

# Laboratório CORE V1

Volume próprio `banco-central-core-v1_core_v1_pgdata`, sem montagem de volumes
do Naruto/C1. Porta publicada apenas em `127.0.0.1:15439` para o executor
Python local; nunca expor em interface pública. Credencial fixa aqui é
exclusivamente sintética. Não colocar este Compose em servidor de produção.

```powershell
docker compose -f homologation/core-v1/compose.yaml config
docker compose -f homologation/core-v1/compose.yaml --profile manual up -d db
docker compose -f homologation/core-v1/compose.yaml exec -T db sh /workspace/schema.sh
$env:CORE_PG_HOST='127.0.0.1'
$env:CORE_PG_PORT='15439'
$env:CORE_PG_DATABASE='core_v1_homolog'
$env:CORE_PG_USER='core_v1'
$env:CORE_PG_PASSWORD='core_v1_synthetic_only'
$env:CORE_PG_SSLMODE='disable'
.venv/Scripts/python.exe -m src.core.runner migrate
.venv/Scripts/python.exe -m src.core.runner run --scope events --min-id 0 --max-id 10000 --as-of 2026-10-22
.venv/Scripts/python.exe -m src.core.runner run --scope combos --min-id 0 --max-id 10000 --as-of 2026-10-22
.venv/Scripts/python.exe -m src.core.runner run --scope orders --min-id 0 --max-id 10000 --as-of 2026-10-22
.venv/Scripts/python.exe -m src.core.runner bulk-inscriptions --min-id 0 --max-id 10000 --chunk-size 10000 --as-of 2026-10-22
$env:CORE_V1_LAB_TEST='1'
.venv/Scripts/python.exe -m pytest tests/integration/test_core_v1_lab.py -q
docker compose -f homologation/core-v1/compose.yaml --profile manual stop db
```

`down` sem `-v` preserva o volume. Exclusão de volume requer autorização
separada. Um rerun completo exige volume novo; `schema.sh` recusa volume
modificado. A suíte de integração exige `CORE_V1_LAB_TEST=1` e verifica o
nome do banco antes de qualquer operação. Nunca apontar as variáveis do
laboratório para `Atendimento`.

`bulk-inscriptions` cria projeções temporárias de sessão para as views Magento
e para a chave de pedido das inscrições Ativo. Uma única materialização evita
reagregar milhões de itens a cada faixa. O primeiro lote é limitado a 1.000
IDs; os demais usam `--chunk-size` (máximo de 100.000 IDs inclusivos). A
conexão deve permanecer aberta durante toda a sequência; falha interrompe o
processamento, preserva lotes já confirmados e registra o lote falho. As
projeções temporárias desaparecem ao encerrar a conexão. RAW/STAGING e o gate
de indicadores não são alterados por essa otimização.

#!/bin/sh
# Executado somente pelo timer aprovado; nunca aceita modo FULL.
set -eu
umask 077

case "${1:-}" in
  magento) entities='sales_order sales_order_item' ;;
  ativo) entities='pedido pedido_evento' ;;
  *) echo 'Grupo D1 inválido' >&2; exit 2 ;;
esac
if [ "$#" -gt 2 ]; then
  echo 'Argumentos D1 inválidos' >&2
  exit 2
fi
if [ "$#" -eq 2 ]; then
  case "$1:$2" in
    magento:sales_order|magento:sales_order_item|ativo:pedido|ativo:pedido_evento)
      entities="$2" ;;
    *) echo 'Entidade D1 inválida' >&2; exit 2 ;;
  esac
fi

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)"
compose_file="$repo_root/deploy/d1/compose.yaml"
config_file=/etc/bcd-d1/compose.env
lock_dir=/var/lib/bcd-d1

if [ ! -f "$config_file" ] || [ ! -d "$lock_dir" ] || [ -L "$lock_dir" ]; then
  echo 'Configuração ou diretório de lock D1 ausente/inválido' >&2
  exit 2
fi

# Lock global no host, além dos advisory locks PostgreSQL por entidade.
exec 9>"$lock_dir/global.lock"
if ! flock -n 9; then
  echo 'Outro grupo D1 já está em execução' >&2
  exit 75
fi

for entity in $entities; do
  docker compose --env-file "$config_file" -f "$compose_file" \
    --profile manual exec -T executor python -m deploy.d1.entrypoint \
    incremental --source "$1" --entity "$entity"
done

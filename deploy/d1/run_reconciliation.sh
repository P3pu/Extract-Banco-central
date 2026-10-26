#!/bin/sh
# Preparado para execução futura sob aprovação; somente Ativo pedido/pedido_evento.
set -eu
umask 077

if [ "$#" -ne 0 ]; then
  echo 'Argumentos de reconciliação inválidos' >&2
  exit 2
fi

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)"
compose_file="$repo_root/deploy/d1/compose.yaml"
config_file=/etc/bcd-d1/compose.env
lock_dir=/var/lib/bcd-d1

if [ ! -f "$config_file" ] || [ -L "$config_file" ] || [ ! -d "$lock_dir" ] || [ -L "$lock_dir" ]; then
  echo 'Configuração ou diretório de lock D1 ausente/inválido' >&2
  exit 2
fi

# O mesmo lock global dos incrementais impede cargas simultâneas no host.
exec 9>"$lock_dir/global.lock"
if ! flock -n 9; then
  echo 'Outra carga D1 já está em execução' >&2
  exit 75
fi

for entity in pedido pedido_evento; do
  docker compose --env-file "$config_file" -f "$compose_file" \
    --profile manual exec -T executor python -m deploy.d1.entrypoint \
    reconcile --entity "$entity"
done

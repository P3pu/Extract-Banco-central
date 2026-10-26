#!/bin/sh
# Executar somente dentro do container db, após autorização explícita.
set -eu
export LC_ALL=C
export PGHOST=/var/run/postgresql
export PGUSER=core_c1
export PGDATABASE=core_c1_homolog

assert_local() {
  actual="$(psql -X -A -t -v ON_ERROR_STOP=1 \
    -h /var/run/postgresql -U core_c1 -d core_c1_homolog -c \
    "SELECT current_database() || ':' || current_user || ':' || (inet_server_addr() IS NULL)::text || ':' || current_setting('server_version_num')")"
  case "$actual" in
    core_c1_homolog:core_c1:true:16*) ;;
    *) echo "Destino local CORE C1 inválido; operação cancelada" >&2; exit 2 ;;
  esac
}

assert_fresh_schema() {
  existing="$(psql -X -A -t -v ON_ERROR_STOP=1 \
    -h /var/run/postgresql -U core_c1 -d core_c1_homolog -c \
    "SELECT COUNT(*) FROM pg_namespace WHERE nspname IN ('raw','staging','core')")"
  if [ "$existing" != 0 ]; then
    echo "Volume já contém esquemas do laboratório; schema cancelado" >&2
    exit 2
  fi
}

apply_file() {
  assert_local
  psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql \
    -U core_c1 -d core_c1_homolog -f "$1"
}

case "${1:-}" in
  schema)
    assert_local
    assert_fresh_schema
    # Ordem lexicográfica inclui 003b e 005b no ponto correto.
    for file in /workspace/sql/postgres/[0-9][0-9][0-9]*.sql; do
      apply_file "$file"
    done
    apply_file /workspace/sql/staging/001_create_staging_schema.sql
    for file in /workspace/sql/staging/magento/[0-9][0-9][0-9]*.sql; do
      apply_file "$file"
    done
    for file in /workspace/sql/staging/ativo/[0-9][0-9][0-9]*.sql; do
      apply_file "$file"
    done
    # Somente neste laboratório: fontes opcionais ainda não integradas à RAW.
    apply_file /workspace/sql/core/proposed/000_missing_sources.sql
    ;;
  seed)
    apply_file /workspace/c1/fixtures.sql
    ;;
  core)
    apply_file /workspace/sql/core/proposed/001_core_ddl.sql
    apply_file /workspace/sql/core/proposed/002_core_helpers.sql
    ;;
  test)
    assert_local
    tr -d '\r' < /workspace/c1/capture_candidates.sh | sh
    apply_file /workspace/c1/tests.psql
    ;;
  *)
    echo "Uso: run.sh {schema|seed|core|test}" >&2
    exit 2
    ;;
esac

#!/bin/sh
# Executar somente no container isolado apos autorizacao especifica.
set -eu
export LC_ALL=C
export PGHOST=/var/run/postgresql
export PGUSER=raw_r1
export PGDATABASE=raw_r1_homolog

psql_local() {
  psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql \
    -U raw_r1 -d raw_r1_homolog "$@"
}

assert_local() {
  actual="$(psql_local -A -t -c \
    "SELECT current_database() || ':' || current_user || ':' ||
            (inet_server_addr() IS NULL)::text || ':' ||
            current_setting('server_version_num')")"
  case "$actual" in
    raw_r1_homolog:raw_r1:true:160013) ;;
    *) echo "Destino RAW R1 invalido; operacao cancelada" >&2; exit 2 ;;
  esac
}

assert_fresh_schema() {
  existing="$(psql_local -A -t -c \
    "SELECT COUNT(*) FROM pg_namespace WHERE nspname='raw'")"
  if [ "$existing" != 0 ]; then
    echo "Schema raw ja existe; criacao cancelada" >&2
    exit 2
  fi
}

apply_file() {
  assert_local
  psql_local -f "$1"
}

index_oid() {
  psql_local -A -t -c \
    "SELECT COALESCE(to_regclass('raw.idx_magento_sales_order_item_order_id')::oid::text,'AUSENTE')"
}

case "${1:-}" in
  schema)
    assert_local
    assert_fresh_schema
    apply_file /workspace/r1/schema.psql
    ;;
  seed)
    apply_file /workspace/r1/seed.sql
    ;;
  index)
    apply_file /workspace/migrations/001_idx_magento_item_order_id_preflight.sql
    # Chamada psql separada; autocommit ligado, sem BEGIN/--single-transaction.
    assert_local
    psql_local -v AUTOCOMMIT=on -f \
      /workspace/migrations/001_idx_magento_item_order_id.sql
    apply_file /workspace/migrations/001_idx_magento_item_order_id_verify.sql
    ;;
  test)
    apply_file /workspace/migrations/001_idx_magento_item_order_id_verify.sql
    apply_file /workspace/r1/tests.psql
    echo "RAW_R1_LOCAL_TESTS_PASSED"
    ;;
  existing)
    assert_local
    before="$(index_oid)"
    if [ "$before" = AUSENTE ]; then
      echo "Indice ausente; teste de existencia cancelado" >&2
      exit 2
    fi
    apply_file /workspace/migrations/001_idx_magento_item_order_id_preflight.sql
    assert_local
    psql_local -v AUTOCOMMIT=on -f \
      /workspace/migrations/001_idx_magento_item_order_id.sql
    apply_file /workspace/migrations/001_idx_magento_item_order_id_verify.sql
    after="$(index_oid)"
    if [ "$before" != "$after" ]; then
      echo "OID do indice mudou na reaplicacao; teste falhou" >&2
      exit 2
    fi
    echo "RAW_R1_EXISTING_INDEX_PASSED oid=$after"
    ;;
  *)
    echo "Uso: run.sh {schema|seed|index|test|existing}" >&2
    exit 2
    ;;
esac

#!/bin/sh
# Exclusivo do volume novo core_v1_pgdata; não reutilizar C1/C1.5.
set -eu
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=core_v1
export PGDATABASE=core_v1_homolog PGPASSWORD=core_v1_synthetic_only
actual="$(psql -XAt -v ON_ERROR_STOP=1 -c \
  "SELECT current_database()||':'||current_user||':'||current_setting('server_version_num')")"
case "$actual" in core_v1_homolog:core_v1:16*) ;; *) exit 2 ;; esac
existing="$(psql -XAt -v ON_ERROR_STOP=1 -c \
  "SELECT count(*) FROM pg_namespace WHERE nspname IN ('raw','staging','core')")"
[ "$existing" = 0 ] || { echo 'Laboratório não está vazio' >&2; exit 2; }
apply() { psql -X -v ON_ERROR_STOP=1 -f "$1" >/dev/null; }
for f in /workspace/sql/postgres/[0-9][0-9][0-9]*.sql; do apply "$f"; done
apply /workspace/sql/staging/001_create_staging_schema.sql
for f in /workspace/sql/staging/magento/[0-9][0-9][0-9]*.sql; do apply "$f"; done
for f in /workspace/sql/staging/ativo/[0-9][0-9][0-9]*.sql; do apply "$f"; done
# Fixtures herdadas de C1 são integralmente sintéticas. O arquivo abaixo
# também cria fontes opcionais de teste, mas a transformação V1 não as lê.
apply /workspace/sql/core/proposed/000_missing_sources.sql
apply /workspace/c1-fixtures.sql
apply /workspace/v1-fixtures-extra.sql
echo CORE_V1_LAB_SCHEMA_SEED_OK

#!/bin/sh
# Gera tabelas TEMP a partir dos SELECTs versionados de 004, sem reescrever a lógica.
# Executado apenas pelo run.sh test dentro do container isolado.
set -eu

source_file=/workspace/sql/core/proposed/004_core_inscricao_candidates.sql
magento_file=/tmp/core_c1_magento_candidate.sql
ativo_file=/tmp/core_c1_ativo_candidate.sql

grep -q '^WITH pais AS MATERIALIZED (' "$source_file"
grep -q '^-- PENDÊNCIAS Magento antes do UPSERT:' "$source_file"
grep -q '^SELECT i.pedido_id, i.inscricao_id, fp.pedido_key,' "$source_file"
grep -q '^WHERE i.pedido_id BETWEEN core.batch_min() AND core.batch_max();$' "$source_file"

{
  printf 'CREATE TEMP TABLE c1_magento_candidate AS\n'
  sed -n '/^WITH pais AS MATERIALIZED (/,/^-- PENDÊNCIAS Magento antes do UPSERT:/p' "$source_file" | sed '$d'
} > "$magento_file"
{
  printf 'CREATE TEMP TABLE c1_ativo_candidate AS\n'
  sed -n '/^SELECT i.pedido_id, i.inscricao_id, fp.pedido_key,/,/^WHERE i.pedido_id BETWEEN core.batch_min() AND core.batch_max();/p' "$source_file"
} > "$ativo_file"

test "$(grep -c '^CREATE TEMP TABLE' "$magento_file")" -eq 1
test "$(grep -c '^CREATE TEMP TABLE' "$ativo_file")" -eq 1
test "$(grep -c ';$' "$magento_file")" -eq 1
test "$(grep -c ';$' "$ativo_file")" -eq 1

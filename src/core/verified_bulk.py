"""Carga CORE V1 por faixas com conferência de cardinalidade e gate.

Não carrega credenciais, não executa FULL e não altera RAW/STAGING.
O chamador deve prover CORE_PG_* por ambiente seguro.
"""
from __future__ import annotations

import argparse
from datetime import date
import time

import psycopg

from src.core import runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-id", type=int, required=True)
    parser.add_argument("--max-id", type=int, required=True)
    parser.add_argument("--chunk-size", type=int, default=20000)
    parser.add_argument("--audit-span", type=int, default=200000)
    parser.add_argument("--max-db-growth-gib", type=float, default=2.0)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--ativo-only", action="store_true")
    parser.add_argument("--approve-production", action="store_true")
    args = parser.parse_args(argv)
    low, high = args.min_id, args.max_id
    if low < 0 or high < low or high > 9223372036854775807:
        parser.error("Faixa inválida")
    if not 1 <= args.chunk_size <= 100000:
        parser.error("Lote deve conter de 1 a 100000 IDs")
    if args.audit_span < args.chunk_size:
        parser.error("Intervalo de auditoria deve cobrir ao menos um lote")
    if args.max_db_growth_gib <= 0:
        parser.error("Limite de crescimento deve ser positivo")

    with runner.connect() as conn:
        runner.validate_destination(conn, args.approve_production)
        if not conn.execute("SELECT pg_try_advisory_lock(21001,1)").fetchone()[0]:
            raise RuntimeError("Outra execução CORE está ativa")
        try:
            runner.schema_contract(conn, "inscriptions")
            conn.execute("SET statement_timeout=300000")
            runner.prepare_inscription_cache(
                conn, magento_low=low if args.ativo_only else None)
            conn.execute("SET statement_timeout=60000")
            baseline = conn.execute(
                "SELECT pg_database_size(current_database())").fetchone()[0]
            audit_low = low
            for current in range(low, high + 1, args.chunk_size):
                upper = min(high, current + args.chunk_size - 1)
                started = time.monotonic()
                if runner.source_range_has_rows(conn, current, upper):
                    batch, count = runner.run_range(
                        conn, "inscriptions", current, upper, args.as_of,
                        cached=True)
                    print("LOAD_OK", current, upper, batch, count,
                          round(time.monotonic() - started, 2), flush=True)
                else:
                    print("LOAD_EMPTY", current, upper, flush=True)
                if upper - audit_low + 1 < args.audit_span and upper != high:
                    continue
                expected_ativo = conn.execute(
                    "SELECT count(*) FROM raw.ativo_pedido_evento "
                    "WHERE id_pedido_evento BETWEEN %s AND %s",
                    (audit_low, upper)).fetchone()[0]
                expected_magento = 0 if args.ativo_only else conn.execute(
                    "SELECT count(*) FROM "
                    "pg_temp.core_v1_magento_inscricao_cache "
                    "WHERE inscricao_id BETWEEN %s AND %s",
                    (audit_low, upper)).fetchone()[0]
                actual = dict(conn.execute(
                    "SELECT origem,count(*) FROM core.fato_inscricao "
                    "WHERE inscricao_id_origem BETWEEN %s AND %s "
                    "GROUP BY origem", (audit_low, upper)).fetchall())
                gate = conn.execute(
                    "SELECT count(*) FROM "
                    "core.fato_inscricao_indicadores_validos").fetchone()[0]
                growth = conn.execute(
                    "SELECT pg_database_size(current_database())"
                ).fetchone()[0] - baseline
                print("AUDIT", audit_low, upper, "SOURCE", expected_ativo,
                      expected_magento, "CORE", actual, "GATE", gate,
                      "GROWTH_MIB", round(growth / 1048576, 1), flush=True)
                if (expected_ativo != actual.get("ativo", 0)
                        or expected_magento != actual.get("magento", 0)):
                    raise RuntimeError("SOURCE_CORE_COUNT_DIVERGENCE")
                if gate != 0:
                    raise RuntimeError("INDICATOR_GATE_OPEN")
                if growth > args.max_db_growth_gib * 1024 ** 3:
                    raise RuntimeError("DB_GROWTH_LIMIT")
                audit_low = upper + 1
            print("LOAD_PHASE_COMPLETE", low, high, flush=True)
        finally:
            try:
                conn.execute("SELECT pg_advisory_unlock(21001,1)")
            except psycopg.Error:
                # Fechar a sessão também libera o lock após queda da conexão.
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

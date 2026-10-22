"""Execução controlada da CORE V1 a partir de views STAGING PostgreSQL.

Não lê MySQL, não é chamada pelo executor D1 e falha fechada em Atendimento.
Uma aprovação operacional separada é exigida antes de qualquer uso em produção.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import os
from pathlib import Path
import sys
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg


ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "sql" / "core" / "v1"
MIGRATIONS = (
    ROOT / "sql/core/proposed/001_core_ddl.sql",
    ROOT / "sql/core/proposed/002_core_helpers.sql",
    SQL / "006_core_v1_extensions.sql",
)
STEPS = {
    "events": ("010_eventos.sql", "011_evento_map.sql",
               "013_invalidate_event_dependents.sql"),
    "combos": ("012_combos.sql", "014_invalidate_combo_dependents.sql"),
    "orders": ("020_pedido_magento.sql", "021_pedido_ativo.sql",
               "022_invalidate_order_dependents.sql", "061_alertas_pedido.sql"),
    "inscriptions": ("030_inscricao_base.sql", "040_inscricao_ativo.sql",
                     "041_inscricao_magento.sql", "050_reconciliacao_pedidos.sql",
                     "060_alertas.sql"),
}
AUDIT_SCOPE = {
    "events": "DIM_EVENTO", "combos": "DIM_COMBO",
    "orders": "PEDIDO_MAGENTO", "inscriptions": "INSCRICAO_DERIVADA",
}
REQUIRED = {
    "staging.ativo_evento": {"evento_id": "int", "data_evento": "text"},
    "staging.magento_evento": {"evento_id": "int", "data_evento": "date"},
    "staging.ativo_combo": {"combo_id": "int"},
    "staging.ativo_pedido": {"pedido_id": "int", "status_id": "int"},
    "staging.magento_pedido": {"pedido_id": "int", "subtotal": "numeric",
                                "desconto": "numeric"},
    "staging.ativo_inscricao": {"inscricao_id": "int", "pedido_id": "int",
                                 "preco": "numeric", "desconto_individual": "text"},
    "staging.magento_inscricao": {"inscricao_id": "int", "pedido_id": "int",
                                   "valor_bruto": "numeric"},
    "staging.magento_item_pedido": {"item_id": "int", "pedido_id": "int"},
    "staging.magento_bundle_componente": {"inscricao_item_id": "int"},
    "staging.magento_pedido_regra": {"pedido_id": "int"},
    "staging.ativo_categoria": {"categoria_id": "int", "valor_kit": "numeric"},
    "staging.ativo_cupom": {"cupom_id": "int", "codigo_cupom": "text"},
    "core.fato_pedido": {"pedido_id_origem": "int", "conteudo_hash": "text",
                         "valor_bruto_pedido": "numeric"},
    "core.fato_inscricao": {"inscricao_id_origem": "int",
                            "conteudo_hash": "text",
                            "dependencias_hash_snapshot": "text",
                            "estado_derivacao": "text"},
}
KINDS = {
    "int": {"smallint", "integer", "bigint"},
    "numeric": {"numeric", "decimal", "real", "double precision"},
    "text": {"text", "character varying", "character"},
    "date": {"date", "timestamp without time zone", "timestamp with time zone"},
}


def require_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"Configuração obrigatória ausente: {key}")
    return value


def connect() -> psycopg.Connection:
    host = require_env("CORE_PG_HOST")
    sslmode = os.environ.get("CORE_PG_SSLMODE", "verify-full")
    if sslmode != "verify-full" and not (
        sslmode == "disable" and host in ("localhost", "127.0.0.1", "::1", "/var/run/postgresql")
    ):
        raise RuntimeError("TLS verify-full obrigatório fora de loopback/socket local")
    return psycopg.connect(
        host=host, port=int(require_env("CORE_PG_PORT")),
        dbname=require_env("CORE_PG_DATABASE"), user=require_env("CORE_PG_USER"),
        password=require_env("CORE_PG_PASSWORD"), sslmode=sslmode,
        sslrootcert=os.environ.get("CORE_PG_SSLROOTCERT") or None,
        connect_timeout=10, application_name="bcd-core-v1",
        options="-c statement_timeout=60000 -c lock_timeout=5000 -c timezone=UTC",
        autocommit=True,
    )


def validate_destination(conn: psycopg.Connection, approve_production: bool) -> None:
    dbname = conn.execute("SELECT current_database()").fetchone()[0]
    expected = require_env("CORE_PG_DATABASE")
    if dbname != expected:
        raise RuntimeError("Destino PostgreSQL inesperado")
    if dbname == "Atendimento" and not (
        approve_production and os.environ.get("CORE_PRODUCTION_APPROVAL") == "CORE_V1_APPROVED"
    ):
        raise RuntimeError("Atendimento bloqueado: aprovação operacional específica ausente")
    if dbname != "Atendimento" and not dbname.startswith("core_v1_"):
        raise RuntimeError("Laboratório CORE deve usar banco core_v1_*")


def schema_contract(conn: psycopg.Connection, scope: str) -> None:
    needed = {k: v for k, v in REQUIRED.items() if scope == "inscriptions" or
              (scope == "events" and k in ("staging.ativo_evento", "staging.magento_evento")) or
              (scope == "combos" and k == "staging.ativo_combo") or
              (scope == "orders" and k in ("staging.ativo_pedido", "staging.magento_pedido"))}
    if scope != "inscriptions":
        needed["core.fato_pedido"] = REQUIRED["core.fato_pedido"]
    for qualified, columns in needed.items():
        schema, table = qualified.split(".")
        rows = conn.execute(
            "SELECT column_name,data_type FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s", (schema, table)
        ).fetchall()
        found = dict(rows)
        for column, kind in columns.items():
            if found.get(column) not in KINDS[kind]:
                raise RuntimeError(f"SCHEMA_DIVERGENTE: {qualified}.{column}")


def unique_source_grain(conn: psycopg.Connection, scope: str, low: int, high: int) -> None:
    views = {
        "events": (("staging.ativo_evento", "evento_id"),
                   ("staging.magento_evento", "evento_id")),
        "combos": (("staging.ativo_combo", "combo_id"),),
        "orders": (("staging.ativo_pedido", "pedido_id"),
                   ("staging.magento_pedido", "pedido_id")),
        "inscriptions": (("staging.ativo_inscricao", "inscricao_id"),
                         ("staging.magento_inscricao", "inscricao_id")),
    }
    # Identificadores são constantes internas, nunca entrada do usuário.
    for view, key in views[scope]:
        query = (f"SELECT 1 FROM {view} WHERE {key} BETWEEN %s AND %s "
                 f"GROUP BY {key} HAVING COUNT(*)>1 LIMIT 1")
        if conn.execute(query, (low, high)).fetchone():
            raise RuntimeError(f"SCHEMA_DIVERGENTE: grão duplicado em {view}")


def validate_range(low: int, high: int) -> None:
    if low < 0 or high < low or high - low >= 100000 or high > 9223372036854775807:
        raise ValueError("Faixa inválida: até 100000 IDs inclusivos")


def error_code(exc: Exception) -> str:
    if isinstance(exc, psycopg.errors.QueryCanceled):
        return "TIMEOUT"
    if isinstance(exc, psycopg.IntegrityError):
        return "CONSTRAINT"
    if isinstance(exc, RuntimeError) and str(exc).startswith("SCHEMA_DIVERGENTE"):
        return "SCHEMA_DIVERGENTE"
    if isinstance(exc, ValueError):
        return "LOTE_INVALIDO"
    return "ERRO_INTERNO"


def migrate(conn: psycopg.Connection) -> None:
    existing = conn.execute("SELECT to_regclass('core.schema_migration')").fetchone()[0]
    if existing is not None:
        applied = dict(conn.execute("SELECT migration_id,sha256 FROM core.schema_migration"))
        for path in MIGRATIONS:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if applied.get(path.name) != digest:
                raise RuntimeError(f"Migration ausente/divergente: {path.name}")
        return
    if conn.execute("SELECT to_regclass('core.fato_pedido')").fetchone()[0] is not None:
        raise RuntimeError("CORE parcial existente: revisão manual necessária")
    for path in MIGRATIONS:
        conn.execute(path.read_text(encoding="utf-8"))
    with conn.transaction():
        for path in MIGRATIONS:
            conn.execute(
                "INSERT INTO core.schema_migration(migration_id,sha256) VALUES (%s,%s)",
                (path.name, hashlib.sha256(path.read_bytes()).hexdigest()),
            )


def run_range(conn: psycopg.Connection, scope: str, low: int, high: int,
              as_of: date) -> tuple[str, int]:
    validate_range(low, high)
    if not conn.execute("SELECT pg_try_advisory_lock(21001,1)").fetchone()[0]:
        raise RuntimeError("Outra execução CORE está ativa")
    batch_id = str(uuid4())
    total = 0
    try:
        with conn.transaction():
            conn.execute(
                "INSERT INTO core.core_etl_execucao "
                "(batch_id,versao_ddl,escopo,status,limite_inferior,limite_superior) "
                "VALUES (%s,'CORE_V1_20261022',%s,'RUNNING',%s,%s)",
                (batch_id, AUDIT_SCOPE[scope], low, high),
            )
        try:
            with conn.transaction():
                schema_contract(conn, scope)
                unique_source_grain(conn, scope, low, high)
                for name in STEPS[scope]:
                    result = conn.execute((SQL / name).read_text(encoding="utf-8"),
                                          {"id_min": low, "id_max": high,
                                           "as_of_date": as_of})
                    total += max(result.rowcount, 0)
                conn.execute(
                    "UPDATE core.core_etl_execucao SET status='SUCCEEDED',"
                    "encerrada_em=clock_timestamp(),linhas_processadas=%s "
                    "WHERE batch_id=%s AND status='RUNNING'", (total, batch_id),
                )
        except Exception as exc:
            with conn.transaction():
                conn.execute(
                    "UPDATE core.core_etl_execucao SET status='FAILED',"
                    "encerrada_em=clock_timestamp(),erro_codigo=%s "
                    "WHERE batch_id=%s AND status='RUNNING'",
                    (error_code(exc), batch_id),
                )
            raise
        return batch_id, total
    finally:
        try:
            conn.execute("SELECT pg_advisory_unlock(21001,1)")
        except psycopg.Error:
            # Encerrar a sessão também libera o lock.
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CORE V1 controlada, sem MySQL")
    parser.add_argument("command", choices=("migrate", "run"))
    parser.add_argument("--scope", choices=tuple(STEPS))
    parser.add_argument("--min-id", type=int)
    parser.add_argument("--max-id", type=int)
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--approve-production", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "run" and (
        args.scope is None or args.min_id is None or args.max_id is None
    ):
        parser.error("run requer --scope, --min-id e --max-id")
    try:
        with connect() as conn:
            validate_destination(conn, args.approve_production)
            if args.command == "migrate":
                migrate(conn)
                print("CORE_V1_MIGRATIONS_OK")
            else:
                batch, count = run_range(conn, args.scope, args.min_id,
                                         args.max_id, args.as_of or
                                         datetime.now(ZoneInfo("America/Sao_Paulo")).date())
                print(f"CORE_V1_RUN_OK batch={batch} linhas_processadas={count}")
        return 0
    except Exception as exc:
        # Apenas tipo/código, nunca detalhes do driver ou SQL com parâmetros.
        print(f"CORE_V1_FAILED {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

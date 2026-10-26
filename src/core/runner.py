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
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg


ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "sql" / "core" / "v1"
MIGRATIONS = (
    ROOT / "sql/core/proposed/001_core_ddl.sql",
    ROOT / "sql/core/proposed/002_core_helpers.sql",
    SQL / "006_core_v1_extensions.sql",
    SQL / "007_core_alerta_zero_id.sql",
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

# Projeções exclusivamente de sessão. Nunca substituem as views STAGING nem
# persistem dados pessoais: a seleção contém só os campos usados pela CORE.
INSCRIPTION_CACHE = (
    ("core_v1_magento_inscricao_cache", """
        SELECT inscricao_id,pedido_id,evento_id,evento_sku,data_evento,
               sku_inscricao,modalidade,categoria_origem,tamanho,status_pedido,
               valor_bruto,batch_id,desconto_item,cupom,estado_pedido
        FROM staging.magento_inscricao
    """, ("inscricao_id", "pedido_id")),
    ("core_v1_magento_bundle_componente_cache", """
        SELECT inscricao_item_id,desconto,valor_linha
        FROM staging.magento_bundle_componente
    """, ("inscricao_item_id",)),
    ("core_v1_magento_pedido_regra_cache", """
        SELECT pedido_id,etiqueta FROM staging.magento_pedido_regra
    """, ("pedido_id",)),
    ("core_v1_magento_bundle_pai_cache", """
        SELECT item_id,pedido_id,eh_bundle,quantidade_pedida,
               quantidade_cancelada,quantidade_reembolsada,valor_linha,desconto
        FROM staging.magento_item_pedido WHERE eh_bundle
    """, ("item_id", "pedido_id")),
    ("core_v1_magento_child_summary_cache", """
        SELECT inscricao_item_id,
               SUM(desconto) FILTER (WHERE desconto IS NOT NULL) desconto,
               COUNT(desconto) qtd_descontos,
               SUM(valor_linha) FILTER (WHERE valor_linha IS NOT NULL) bruto
        FROM pg_temp.core_v1_magento_bundle_componente_cache
        GROUP BY inscricao_item_id
    """, ("inscricao_item_id",)),
    ("core_v1_magento_order_summary_cache", """
        SELECT pai.pedido_id,
               SUM(CASE WHEN cf.desconto IS NOT NULL AND cf.desconto<>0
                        THEN cf.desconto ELSE COALESCE(pai.desconto,0) END)
                   desconto_itens,
               SUM(CASE WHEN pai.valor_linha IS NOT NULL
                             AND pai.valor_linha<>0 THEN pai.valor_linha
                        ELSE cf.bruto END) bruto_itens,
               COUNT(*) qtd_bundles,
               BOOL_AND(pai.desconto IS NOT NULL OR cf.desconto IS NOT NULL)
                   componentes_presentes
        FROM pg_temp.core_v1_magento_bundle_pai_cache pai
        LEFT JOIN pg_temp.core_v1_magento_child_summary_cache cf
          ON cf.inscricao_item_id=pai.item_id
        GROUP BY pai.pedido_id
    """, ("pedido_id",)),
    ("core_v1_ativo_inscricao_count_cache", """
        SELECT id_pedido AS pedido_id,COUNT(*) AS qtd_staging
        FROM raw.ativo_pedido_evento GROUP BY id_pedido
    """, ("pedido_id",)),
    ("core_v1_batch_pedidos_cache", """
        SELECT NULL::text AS origem,NULL::bigint AS pedido_id_origem
        WHERE false
    """, ("origem,pedido_id_origem",)),
    ("core_v1_batch_magento_inscricao_cache", """
        SELECT inscricao_key,origem,inscricao_id_origem,conteudo_hash,
               flag_evento_teste,flag_evento_nao_mapeado,
               flag_pedido_nao_encontrado,data_evento
        FROM core.fato_inscricao WHERE false
    """, ("inscricao_id_origem",)),
)
CACHE_REFS = {
    "staging.magento_inscricao": "pg_temp.core_v1_magento_inscricao_cache",
    "staging.magento_bundle_componente":
        "pg_temp.core_v1_magento_bundle_componente_cache",
    "staging.magento_pedido_regra": "pg_temp.core_v1_magento_pedido_regra_cache",
    "staging.magento_item_pedido": "pg_temp.core_v1_magento_bundle_pai_cache",
}
COVERAGE_CTE = """ativo_cobertura AS (
    SELECT 'ativo'::text origem,i.pedido_id,COUNT(*) qtd_staging
    FROM staging.ativo_inscricao i
    WHERE i.pedido_id IN (SELECT pedido_id_origem FROM pedidos
                          WHERE origem='ativo')
    GROUP BY i.pedido_id
)"""
COVERAGE_CTE_CACHED = """ativo_cobertura AS (
    SELECT 'ativo'::text origem,i.pedido_id,i.qtd_staging
    FROM pg_temp.core_v1_ativo_inscricao_count_cache i
    WHERE i.pedido_id IN (SELECT pedido_id_origem FROM pedidos
                          WHERE origem='ativo')
)"""
PEDIDOS_CTE_CACHED = """WITH pedidos AS (
    SELECT origem,pedido_id_origem
    FROM pg_temp.core_v1_batch_pedidos_cache
"""


def replace_cte(body: str, start_marker: str, end_marker: str,
                replacement: str) -> str:
    if body.count(start_marker) != 1 or body.count(end_marker) != 1:
        raise RuntimeError("Contrato de CTE CORE mudou")
    start = body.index(start_marker)
    end = body.index(end_marker, start)
    return body[:start] + replacement + body[end:]


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
        options=("-c statement_timeout=60000 -c lock_timeout=5000 "
                 "-c idle_in_transaction_session_timeout=120000 -c timezone=UTC"),
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


def unique_source_grain(conn: psycopg.Connection, scope: str, low: int, high: int,
                        cached: bool = False) -> None:
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
        if cached and view == "staging.magento_inscricao":
            view = CACHE_REFS[view]
        query = (f"SELECT 1 FROM {view} WHERE {key} BETWEEN %s AND %s "
                 f"GROUP BY {key} HAVING COUNT(*)>1 LIMIT 1")
        if conn.execute(query, (low, high)).fetchone():
            raise RuntimeError(f"SCHEMA_DIVERGENTE: grão duplicado em {view}")


def validate_range(low: int, high: int) -> None:
    if low < 0 or high < low or high - low >= 100000 or high > 9223372036854775807:
        raise ValueError("Faixa inválida: até 100000 IDs inclusivos")


def prepare_inscription_cache(conn: psycopg.Connection,
                              magento_low: int | None = None) -> None:
    """Materializa uma só vez as projeções caras, sem estruturas permanentes."""
    if conn.execute("SELECT to_regclass('pg_temp.core_v1_magento_inscricao_cache')")\
            .fetchone()[0] is not None:
        raise RuntimeError("Cache de sessão já existe; abrir conexão nova")
    if magento_low is not None:
        max_item = conn.execute(
            "SELECT max(item_id) FROM raw.magento_sales_order_item"
        ).fetchone()[0]
        if max_item is not None and magento_low <= max_item:
            raise RuntimeError("Faixa ainda pode conter Magento; cache completo obrigatório")
    for name, query, indexes in INSCRIPTION_CACHE:
        print(f"CORE_V1_CACHE_START {name}", flush=True)
        if magento_low is not None and name.startswith("core_v1_magento_"):
            query = f"SELECT * FROM ({query}) AS fonte WHERE false"
        with conn.transaction():
            conn.execute(f"CREATE TEMP TABLE {name} ON COMMIT PRESERVE ROWS AS {query}")
            for column in indexes:
                conn.execute(f"CREATE INDEX ON {name}({column})")
            conn.execute(f"ANALYZE {name}")
        print(f"CORE_V1_CACHE_OK {name}", flush=True)


def refresh_batch_pedidos(conn: psycopg.Connection, low: int, high: int) -> None:
    """Atualiza somente o inventário temporário dos pedidos deste lote."""
    conn.execute("TRUNCATE pg_temp.core_v1_batch_pedidos_cache")
    conn.execute("""
        INSERT INTO pg_temp.core_v1_batch_pedidos_cache
            (origem,pedido_id_origem)
        SELECT origem,pedido_id_origem
        FROM core.fato_inscricao
        WHERE origem='ativo'
          AND inscricao_id_origem BETWEEN %s AND %s
          AND pedido_id_origem IS NOT NULL
        UNION
        SELECT origem,pedido_id_origem
        FROM core.fato_inscricao
        WHERE origem='magento'
          AND inscricao_id_origem BETWEEN %s AND %s
          AND pedido_id_origem IS NOT NULL
    """, (low, high, low, high))
    conn.execute("ANALYZE pg_temp.core_v1_batch_pedidos_cache")


def refresh_batch_magento(conn: psycopg.Connection, low: int, high: int) -> None:
    """Expõe ao planner o grão Magento já inserido nesta transação."""
    conn.execute("TRUNCATE pg_temp.core_v1_batch_magento_inscricao_cache")
    conn.execute("""
        INSERT INTO pg_temp.core_v1_batch_magento_inscricao_cache
            (inscricao_key,origem,inscricao_id_origem,conteudo_hash,
             flag_evento_teste,flag_evento_nao_mapeado,
             flag_pedido_nao_encontrado,data_evento)
        SELECT inscricao_key,origem,inscricao_id_origem,conteudo_hash,
               flag_evento_teste,flag_evento_nao_mapeado,
               flag_pedido_nao_encontrado,data_evento
        FROM core.fato_inscricao
        WHERE origem='magento'
          AND inscricao_id_origem BETWEEN %s AND %s
    """, (low, high))
    conn.execute("ANALYZE pg_temp.core_v1_batch_magento_inscricao_cache")


def inscription_sql(name: str, cached: bool) -> str:
    body = (SQL / name).read_text(encoding="utf-8")
    if not cached:
        return body
    for source, target in CACHE_REFS.items():
        body = body.replace(source, target)
    if name == "041_inscricao_magento.sql":
        old = ("FROM core.fato_inscricao f\n"
               "    JOIN pg_temp.core_v1_magento_inscricao_cache i")
        new = ("FROM pg_temp.core_v1_batch_magento_inscricao_cache f\n"
               "    JOIN pg_temp.core_v1_magento_inscricao_cache i")
        if body.count(old) != 1:
            raise RuntimeError("Contrato da derivação Magento mudou")
        body = body.replace(old, new)
        body = replace_cte(
            body, "WITH filhos AS (", "), regras AS (",
            """WITH filhos AS (
    SELECT inscricao_item_id,desconto,qtd_descontos,bruto
    FROM pg_temp.core_v1_magento_child_summary_cache
    WHERE inscricao_item_id BETWEEN %(id_min)s AND %(id_max)s
""")
        body = replace_cte(
            body, "conciliacao AS (", "), final AS (",
            """conciliacao AS (
    SELECT pedido_id,desconto_itens,bruto_itens,qtd_bundles,
           componentes_presentes
    FROM pg_temp.core_v1_magento_order_summary_cache
    WHERE pedido_id IN (SELECT DISTINCT pedido_id FROM base)
""")
    if name == "050_reconciliacao_pedidos.sql":
        body = replace_cte(
            body, "WITH pedidos AS (", "), magento_itens AS (",
            PEDIDOS_CTE_CACHED)
        body = replace_cte(
            body, "magento_itens AS (", "), eventos AS (",
            """magento_itens AS (
    SELECT 'magento'::text origem,pedido_id,desconto_itens,bruto_itens,qtd_bundles
    FROM pg_temp.core_v1_magento_order_summary_cache
    WHERE pedido_id IN (SELECT pedido_id_origem FROM pedidos
                        WHERE origem='magento')
""")
        if body.count(COVERAGE_CTE) != 1:
            raise RuntimeError("Contrato da reconciliação Ativo mudou")
        body = body.replace(COVERAGE_CTE, COVERAGE_CTE_CACHED)
    return body


def source_range_has_rows(conn: psycopg.Connection, low: int, high: int) -> bool:
    return conn.execute("""
        SELECT EXISTS (SELECT 1 FROM raw.ativo_pedido_evento
                       WHERE id_pedido_evento BETWEEN %s AND %s)
            OR EXISTS (SELECT 1 FROM pg_temp.core_v1_magento_inscricao_cache
                       WHERE inscricao_id BETWEEN %s AND %s)
    """, (low, high, low, high)).fetchone()[0]


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
        for path in MIGRATIONS[:-1]:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if applied.get(path.name) != digest:
                raise RuntimeError(f"Migration ausente/divergente: {path.name}")
        extension = MIGRATIONS[-1]
        digest = hashlib.sha256(extension.read_bytes()).hexdigest()
        if extension.name in applied:
            if applied[extension.name] != digest:
                raise RuntimeError(f"Migration divergente: {extension.name}")
            return
        with conn.transaction():
            conn.execute(extension.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO core.schema_migration(migration_id,sha256) VALUES (%s,%s)",
                (extension.name, digest),
            )
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
              as_of: date, cached: bool = False) -> tuple[str, int]:
    validate_range(low, high)
    if cached and (scope != "inscriptions" or conn.execute(
            "SELECT to_regclass('pg_temp.core_v1_magento_inscricao_cache')"
            ).fetchone()[0] is None):
        raise RuntimeError("Cache de inscrições ausente/incompatível")
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
                if cached:
                    unique_source_grain(conn, scope, low, high, cached=True)
                else:
                    unique_source_grain(conn, scope, low, high)
                for name in STEPS[scope]:
                    started = time.monotonic()
                    if cached and name == "041_inscricao_magento.sql":
                        refresh_batch_magento(conn, low, high)
                    if cached and name == "050_reconciliacao_pedidos.sql":
                        refresh_batch_pedidos(conn, low, high)
                    result = conn.execute(inscription_sql(name, cached),
                                          {"id_min": low, "id_max": high,
                                           "as_of_date": as_of})
                    total += max(result.rowcount, 0)
                    print(f"CORE_V1_STEP_OK {scope} {low} {high} {name} "
                          f"seconds={time.monotonic() - started:.2f}", flush=True)
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


def run_bulk_inscriptions(conn: psycopg.Connection, low: int, high: int,
                          chunk_size: int, as_of: date) -> tuple[int, int]:
    if low < 0 or high < low or high > 9223372036854775807:
        raise ValueError("Faixa total inválida")
    if not 1 <= chunk_size <= 100000:
        raise ValueError("Lote deve conter de 1 a 100000 IDs")
    if not conn.execute("SELECT pg_try_advisory_lock(21001,1)").fetchone()[0]:
        raise RuntimeError("Outra execução CORE está ativa")
    completed = 0
    processed = 0
    try:
        schema_contract(conn, "inscriptions")
        # Limite mais longo só para construir as projeções temporárias uma vez.
        conn.execute("SET statement_timeout=300000")
        prepare_inscription_cache(conn)
        conn.execute("SET statement_timeout=60000")
        cursor = low
        first = True
        while cursor <= high:
            size = min(chunk_size, 1000) if first else chunk_size
            upper = min(high, cursor + size - 1)
            first = False
            if source_range_has_rows(conn, cursor, upper):
                batch, count = run_range(conn, "inscriptions", cursor, upper,
                                         as_of, cached=True)
                completed += 1
                processed += count
                print(f"CORE_V1_BULK_OK {cursor} {upper} {batch} {count}", flush=True)
            else:
                print(f"CORE_V1_BULK_EMPTY {cursor} {upper}", flush=True)
            cursor = upper + 1
        return completed, processed
    finally:
        try:
            conn.execute("SELECT pg_advisory_unlock(21001,1)")
        except psycopg.Error:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CORE V1 controlada, sem MySQL")
    parser.add_argument("command", choices=("migrate", "run", "bulk-inscriptions"))
    parser.add_argument("--scope", choices=tuple(STEPS))
    parser.add_argument("--min-id", type=int)
    parser.add_argument("--max-id", type=int)
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--chunk-size", type=int, default=100000)
    parser.add_argument("--approve-production", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "run" and (
        args.scope is None or args.min_id is None or args.max_id is None
    ):
        parser.error("run requer --scope, --min-id e --max-id")
    if args.command == "bulk-inscriptions" and (
        args.min_id is None or args.max_id is None or args.scope is not None
    ):
        parser.error("bulk-inscriptions requer --min-id/--max-id, sem --scope")
    try:
        with connect() as conn:
            validate_destination(conn, args.approve_production)
            if args.command == "migrate":
                migrate(conn)
                print("CORE_V1_MIGRATIONS_OK")
            elif args.command == "run":
                batch, count = run_range(conn, args.scope, args.min_id,
                                         args.max_id, args.as_of or
                                         datetime.now(ZoneInfo("America/Sao_Paulo")).date())
                print(f"CORE_V1_RUN_OK batch={batch} linhas_processadas={count}")
            else:
                batches, count = run_bulk_inscriptions(
                    conn, args.min_id, args.max_id, args.chunk_size,
                    args.as_of or datetime.now(ZoneInfo("America/Sao_Paulo")).date())
                print(f"CORE_V1_BULK_COMPLETE lotes={batches} linhas_processadas={count}")
        return 0
    except Exception as exc:
        # Apenas tipo/código, nunca detalhes do driver ou SQL com parâmetros.
        print(f"CORE_V1_FAILED {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

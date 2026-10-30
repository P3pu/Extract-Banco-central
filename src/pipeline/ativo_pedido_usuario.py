"""Preenche raw.ativo_pedido.id_usuario (comprador) nos pedidos já carregados.

Uso único, supervisionado, com a automação parada: aplica a migração 039,
copia (id_pedido, id_usuario) do MySQL por PK e só aplica NOT NULL quando
nenhum pedido ficar sem comprador. Retoma do primeiro pedido ainda NULL.
Não lê nem registra dados pessoais: apenas IDs.
"""

import argparse
import json
from datetime import datetime, timezone
from time import monotonic

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.pipeline.ativo_pedido import ENTITIES

LOCK_ID = ENTITIES["pedido"][1]
MIGRATION = ROOT / "sql/postgres/039_add_ativo_pedido_id_usuario.sql"


def log(event, **fields):
    print(json.dumps({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                      "source": "ativo", "table": "sa_pedido", "column": "id_usuario",
                      **fields}, default=str), flush=True)


def page_query(batch_size, upper_id, cursor):
    if batch_size <= 0 or upper_id is None:
        raise ValueError("Lote ou limite inválido")
    return ("SELECT id_pedido, id_usuario FROM sa_pedido FORCE INDEX (PRIMARY) "
            "WHERE id_pedido > %s AND id_pedido <= %s ORDER BY id_pedido LIMIT %s",
            (cursor, upper_id, batch_size))


def apply_page(connection, rows):
    connection.execute("CREATE TEMP TABLE IF NOT EXISTS pedido_usuario "
                       "(id_pedido INTEGER PRIMARY KEY, id_usuario INTEGER NOT NULL)")
    connection.execute("TRUNCATE pg_temp.pedido_usuario")
    with connection.cursor().copy(
            "COPY pg_temp.pedido_usuario (id_pedido, id_usuario) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
    return connection.execute(
        "UPDATE raw.ativo_pedido p SET id_usuario=u.id_usuario "
        "FROM pg_temp.pedido_usuario u WHERE p.id_pedido=u.id_pedido "
        "AND p.id_usuario IS DISTINCT FROM u.id_usuario").rowcount


def run(settings, batch_size=10_000):
    started = monotonic()
    progress = {"rows_read": 0, "rows_updated": 0}
    with postgres.connect(settings) as connection:
        if not connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
            raise RuntimeError("Já existe carga sa_pedido em execução")
        try:
            connection.execute(MIGRATION.read_text(encoding="utf-8"))
            connection.commit()
            first, upper_id, missing = connection.execute(
                "SELECT min(id_pedido) FILTER (WHERE id_usuario IS NULL), max(id_pedido), "
                "count(*) FILTER (WHERE id_usuario IS NULL) FROM raw.ativo_pedido").fetchone()
            log("started", first_missing=first, upper_id=upper_id, missing=missing)
            if first is not None:
                cursor = first - 1
                with mysql.connect(settings, "ativo") as reader:
                    while True:
                        query, params = page_query(batch_size, upper_id, cursor)
                        with reader._connection.cursor() as source:
                            source.execute(query, params)
                            rows = source.fetchall()
                        if not rows:
                            break
                        progress["rows_read"] += len(rows)
                        progress["rows_updated"] += apply_page(connection, rows)
                        connection.commit()
                        cursor = rows[-1][0]
                        log("batch", cursor=cursor, **progress)
            missing = connection.execute(
                "SELECT count(*) FROM raw.ativo_pedido WHERE id_usuario IS NULL").fetchone()[0]
            if missing:
                # Pedido removido do MySQL ou fora do limite: revisar antes do NOT NULL.
                raise RuntimeError(f"{missing} pedidos RAW sem comprador na origem")
            connection.execute("SET LOCAL statement_timeout='15min'")
            connection.execute("ALTER TABLE raw.ativo_pedido ALTER COLUMN id_usuario SET NOT NULL")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            if not connection.closed:
                connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
    log("success", duration_seconds=round(monotonic() - started, 2), **progress)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--batch-size", type=int, default=10_000)
    args = parser.parse_args(argv)
    run(Settings.load(), args.batch_size)


if __name__ == "__main__":
    main()

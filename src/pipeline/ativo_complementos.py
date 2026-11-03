"""Itens de produto, endereços e cabeçalhos de cupom Ativo, com paginação por PK e carga transacional."""

import json
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from psycopg import sql

from src.config.settings import ROOT
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.pipeline.text_sanitizer import replace_nul
from src.sources.ativo import complementos

ENTITIES = {
    "pedido_produto": (complementos.pedido_produto, 7248319318,
                       "021_create_ativo_pedido_produto_raw.sql"),
    "pedido_endereco": (complementos.pedido_endereco, 7248319319,
                        "022_create_ativo_pedido_endereco_raw.sql"),
    "cupom_desconto": (complementos.cupom_desconto, 7248319321,
                       "038_create_ativo_cupom_desconto_raw.sql"),
}
SNAPSHOT_ENTITIES = {"pedido_produto", "cupom_desconto"}


def log(event, entity, **fields):
    print(json.dumps({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                      "source": "ativo", "table": f"sa_{entity}", **fields}, default=str), flush=True)


def load(connection, reader, mode, batch_size, batch_id, old_id, days, progress, entity):
    contract, _, ddl = ENTITIES[entity]
    target = ("raw", f"ativo_{entity}")
    source_count, upper_id = reader.snapshot_bounds(
        contract, count_total=mode in {"FULL", "SNAPSHOT"})
    cutoff = reader.ativo_pedido_cutoff(days) if mode == "RECONCILIATION" else None
    if mode in {"FULL", "SNAPSHOT"}:
        connection.execute((ROOT / "sql/postgres" / ddl).read_text(encoding="utf-8"))
    else:
        loader.validate_target(connection, target, contract)
    loader.prepare(connection, target)
    cursor = None
    newest = None if mode in {"FULL", "SNAPSHOT"} else old_id
    while upper_id is not None:
        if mode == "RECONCILIATION":
            rows = reader.pedido_endereco_reconcile_page(
                contract, cutoff=cutoff, upper_id=upper_id,
                batch_size=batch_size, cursor=cursor)
        else:
            rows = reader.snapshot_page(
                contract, batch_size=batch_size, upper_id=upper_id,
                cursor=old_id if cursor is None and mode == "INCREMENTAL" else cursor)
        if not rows:
            break
        progress["rows_extracted"] += len(rows)
        cleaned, nul_count = replace_nul(rows)
        if nul_count:
            progress["nul_replacements"] = progress.get("nul_replacements", 0) + nul_count
        progress["rows_loaded"] += loader.upsert(
            connection, cleaned, batch_id, target, columns=contract.COLUMNS,
            pk=contract.PK, source="ativo")
        cursor = rows[-1][0]
        if mode != "RECONCILIATION":
            newest = max(newest, cursor) if newest is not None else cursor
        log("batch", entity, batch_id=batch_id, mode=mode, **progress)
    if mode in {"FULL", "SNAPSHOT"}:
        if source_count != progress["rows_extracted"]:
            raise ValueError("Contagem de origem divergente; carga revertida")
        if mode == "SNAPSHOT":
            removed = connection.execute(
                sql.SQL("DELETE FROM {} WHERE _batch_id IS DISTINCT FROM %s")
                .format(sql.Identifier(*target)), (batch_id,)).rowcount
            progress["rows_removed"] = removed
        destination_count = connection.execute(
            sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(*target))).fetchone()[0]
        if source_count != destination_count:
            raise ValueError("Contagem origem/destino divergente; carga revertida")
        log("validated", entity, batch_id=batch_id, mode=mode,
            source_count=source_count, destination_count=destination_count,
            **({"rows_removed": progress["rows_removed"]} if mode == "SNAPSHOT" else {}))
    return newest


def run(settings, mode, batch_size=None, days=None, entity="pedido_produto"):
    batch_size = settings.batch_size if batch_size is None else batch_size
    days = settings.reconciliation_days if days is None else days
    allowed = {"pedido_produto": {"FULL", "INCREMENTAL", "SNAPSHOT"},
               "pedido_endereco": {"FULL", "INCREMENTAL", "RECONCILIATION"},
               "cupom_desconto": {"FULL", "SNAPSHOT"}}
    if entity not in allowed or mode not in allowed[entity] or batch_size <= 0 or days <= 0:
        raise ValueError("Modo, lote ou entidade inválidos")
    batch_id = uuid4()
    started = monotonic()
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    contract, lock_id, _ = ENTITIES[entity]
    key = (f"raw.ativo_{entity}", "ativo", contract.TABLE)
    with postgres.connect(settings) as connection:
        if not connection.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,)).fetchone()[0]:
            raise RuntimeError(f"Já existe carga {contract.TABLE} em execução")
        connection.execute(
            "INSERT INTO raw._etl_runs (batch_id,pipeline_name,source_system,source_table,mode,status) "
            "VALUES (%s,%s,%s,%s,%s,'RUNNING')", (batch_id, *key, mode))
        connection.commit()
        try:
            row = connection.execute(
                "SELECT watermark_value FROM raw._etl_watermark WHERE pipeline_name=%s "
                "AND source_system=%s AND source_table=%s", key).fetchone()
            old = int(row[0]) if row and row[0] is not None else None
            if mode in {"INCREMENTAL", "RECONCILIATION"} and old is None:
                raise ValueError("Execute FULL ou SNAPSHOT antes de incremental/reconcile")
            log("started", entity, batch_id=batch_id, mode=mode, previous_watermark=old,
                **({"days": days} if mode == "RECONCILIATION" else {}))
            with mysql.connect(settings, "ativo") as reader:
                database = settings.database("ativo").database
                contract.validate_schema(reader.columns(database, contract.TABLE),
                                         reader.indexes(database, contract.TABLE))
                newest = load(connection, reader, mode, batch_size, batch_id,
                              old, days, progress, entity)
            strategy = "pk+snapshot" if entity in SNAPSHOT_ENTITIES else "pk+reconciliation"
            connection.execute(
                "INSERT INTO raw._etl_watermark (pipeline_name,source_system,source_table,strategy,"
                "watermark_column,watermark_value,last_success_at) VALUES (%s,%s,%s,%s,"
                "%s,%s,clock_timestamp()) ON CONFLICT (pipeline_name,source_system,source_table) "
                "DO UPDATE SET strategy=EXCLUDED.strategy,watermark_column=EXCLUDED.watermark_column,"
                "watermark_value=EXCLUDED.watermark_value,last_success_at=clock_timestamp(),"
                "updated_at=clock_timestamp()",
                (*key, strategy, contract.PK, str(newest) if newest is not None else None))
            connection.execute(
                "UPDATE raw._etl_runs SET status='SUCCESS',finished_at=clock_timestamp(),"
                "rows_extracted=%s,rows_loaded=%s WHERE batch_id=%s",
                (progress["rows_extracted"], progress["rows_loaded"], batch_id))
            connection.commit()
        except BaseException as exc:
            connection.rollback()
            connection.execute(
                "UPDATE raw._etl_runs SET status='FAILED',finished_at=clock_timestamp(),"
                "rows_extracted=%s,rows_loaded=0,error_message=%s WHERE batch_id=%s AND status='RUNNING'",
                (progress["rows_extracted"], type(exc).__name__, batch_id))
            connection.commit()
            log("failed", entity, batch_id=batch_id, mode=mode,
                error=type(exc).__name__, duration_seconds=round(monotonic()-started, 2))
            raise
        finally:
            if not connection.closed:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        log("success", entity, batch_id=batch_id, mode=mode, new_watermark=newest,
            duration_seconds=round(monotonic()-started, 2), **progress)
    return batch_id

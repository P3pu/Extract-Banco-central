"""Pedidos e inscrições Ativo: FULL, incremental por PK e reconciliação."""
import json
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from psycopg import sql

from src.config.settings import ROOT
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.ativo import pedido, pedido_evento

ENTITIES = {
    "pedido": (pedido, 7248319301, "004_create_ativo_raw.sql"),
    "pedido_evento": (pedido_evento, 7248319302, "005_create_ativo_pedido_evento_raw.sql"),
}


def log(event, **fields):
    print(json.dumps({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                      "source": "ativo", "table": "sa_pedido", **fields}, default=str), flush=True)


def load(connection, reader, mode, batch_size, batch_id, old_id, days, progress, entity="pedido"):
    contract, _, ddl = ENTITIES[entity]
    target = ("raw", f"ativo_{entity}")
    if mode != "FULL":
        loader.validate_target(connection, target, contract)
    count, upper_id = getattr(reader, f"ativo_{entity}_bounds")(count_total=mode == "FULL")
    cutoff = reader.ativo_pedido_cutoff(days) if mode == "RECONCILIATION" else None
    if mode == "FULL":
        connection.execute((ROOT / "sql/postgres" / ddl).read_text(encoding="utf-8"))
        if entity == "pedido_evento":
            connection.execute((ROOT / "sql/postgres/005b_migrate_ativo_pedido_evento_fl_amigo.sql")
                               .read_text(encoding="utf-8"))
    loader.prepare(connection, target)
    cursor = None
    newest = old_id
    while upper_id is not None:
        rows = getattr(reader, f"ativo_{entity}_page")(
            mode=mode, batch_size=batch_size, upper_id=upper_id,
            cursor=old_id if cursor is None and mode == "INCREMENTAL" else cursor,
            cutoff=cutoff)
        if not rows:
            break
        progress["rows_extracted"] += len(rows)
        progress["rows_loaded"] += loader.upsert(connection, rows, batch_id, target,
                                                 columns=contract.COLUMNS, pk=contract.PK, source="ativo")
        last = rows[-1]
        cursor = (last[contract.COLUMNS.index("dt_pedido")], last[0]) if mode == "RECONCILIATION" and entity == "pedido" else last[0]
        if mode != "RECONCILIATION":
            newest = max(newest, last[0]) if newest is not None else last[0]
        log("batch", batch_id=batch_id, table=f"sa_{entity}", mode=mode, **progress)
    if mode == "FULL":
        destination = connection.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(*target))).fetchone()[0]
        if count != progress["rows_extracted"] or count != destination:
            raise ValueError("Contagem origem/destino divergente; carga revertida")
        log("validated", batch_id=batch_id, table=f"sa_{entity}", source_count=count, destination_count=destination)
    return newest


def run(settings, mode, batch_size=None, days=None, entity="pedido"):
    batch_size = settings.batch_size if batch_size is None else batch_size
    days = settings.reconciliation_days if days is None else days
    if mode not in {"FULL", "INCREMENTAL", "RECONCILIATION"} or batch_size <= 0 or days <= 0 or entity not in ENTITIES:
        raise ValueError("Modo, lote ou janela inválidos")
    batch_id = uuid4()
    started = monotonic()
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    contract, lock_id, _ = ENTITIES[entity]
    key = (f"raw.ativo_{entity}", "ativo", f"sa_{entity}")
    with postgres.connect(settings) as connection:
        if not connection.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,)).fetchone()[0]:
            raise RuntimeError(f"Já existe carga sa_{entity} em execução")
        connection.execute(
            "INSERT INTO raw._etl_runs (batch_id,pipeline_name,source_system,source_table,mode,status) "
            "VALUES (%s,%s,%s,%s,%s,'RUNNING')", (batch_id, *key, mode))
        connection.commit()
        try:
            row = connection.execute(
                "SELECT watermark_value FROM raw._etl_watermark WHERE pipeline_name=%s "
                "AND source_system=%s AND source_table=%s", key).fetchone()
            old = int(row[0]) if row and row[0] is not None else None
            if mode != "FULL" and old is None:
                raise ValueError("Execute FULL antes de incremental/reconcile")
            log("started", batch_id=batch_id, table=f"sa_{entity}", mode=mode, previous_watermark=old,
                **({"days": days} if mode == "RECONCILIATION" else {}))
            with mysql.connect(settings, "ativo") as reader:
                db = settings.database("ativo").database
                contract.validate_schema(reader.columns(db, f"sa_{entity}"), reader.indexes(db, f"sa_{entity}"))
                newest = load(connection, reader, mode, batch_size, batch_id, old, days, progress, entity=entity)
            connection.execute(
                "INSERT INTO raw._etl_watermark (pipeline_name,source_system,source_table,strategy,"
                "watermark_column,watermark_value,last_success_at) VALUES (%s,%s,%s,'pk+reconciliation',"
                "%s,%s,clock_timestamp()) ON CONFLICT (pipeline_name,source_system,source_table) "
                "DO UPDATE SET watermark_column=EXCLUDED.watermark_column,"
                "watermark_value=EXCLUDED.watermark_value,last_success_at=clock_timestamp(),"
                "updated_at=clock_timestamp()", (*key, contract.PK, str(newest) if newest is not None else None))
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
            log("failed", batch_id=batch_id, table=f"sa_{entity}", mode=mode, error=type(exc).__name__,
                duration_seconds=round(monotonic()-started, 2))
            raise
        finally:
            if not connection.closed:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        log("success", batch_id=batch_id, table=f"sa_{entity}", mode=mode, new_watermark=newest,
            duration_seconds=round(monotonic()-started, 2), **progress)
    return batch_id

"""Snapshots referenciais Ativo, com substituição lógica transacional."""

import json
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from psycopg import sql

from src.config.settings import ROOT
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.ativo import evento

ENTITIES = {"evento": (evento, 7248319303, "006_create_ativo_evento_raw.sql")}


def log(event, **fields):
    print(json.dumps({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                      "source": "ativo", "table": "sa_evento", **fields}, default=str), flush=True)


def load(connection, reader, batch_size, batch_id, progress, entity="evento"):
    contract, _, ddl = ENTITIES[entity]
    target = ("raw", f"ativo_{entity}")
    source_count, upper_id = getattr(reader, f"ativo_{entity}_bounds")()
    connection.execute((ROOT / "sql/postgres" / ddl).read_text(encoding="utf-8"))
    loader.prepare(connection, target)
    cursor = None
    while upper_id is not None:
        rows = getattr(reader, f"ativo_{entity}_page")(
            batch_size=batch_size, upper_id=upper_id, cursor=cursor)
        if not rows:
            break
        progress["rows_extracted"] += len(rows)
        progress["rows_loaded"] += loader.upsert(
            connection, rows, batch_id, target, columns=contract.COLUMNS,
            pk=contract.PK, source="ativo")
        cursor = rows[-1][0]
        log("batch", batch_id=batch_id, mode="SNAPSHOT", **progress)
    if source_count != progress["rows_extracted"]:
        raise ValueError("Contagem de origem divergente; snapshot revertido")
    removed = connection.execute(
        sql.SQL("DELETE FROM {} WHERE _batch_id IS DISTINCT FROM %s")
        .format(sql.Identifier(*target)), (batch_id,)).rowcount
    destination_count = connection.execute(
        sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(*target))).fetchone()[0]
    if destination_count != source_count:
        raise ValueError("Contagem origem/destino divergente; snapshot revertido")
    log("validated", batch_id=batch_id, mode="SNAPSHOT", source_count=source_count,
        destination_count=destination_count, rows_removed=removed)
    return removed


def run(settings, batch_size=None, entity="evento"):
    batch_size = settings.batch_size if batch_size is None else batch_size
    if batch_size <= 0 or entity not in ENTITIES:
        raise ValueError("Entidade ou lote inválido")
    batch_id = uuid4()
    started = monotonic()
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    contract, lock_id, _ = ENTITIES[entity]
    key = (f"raw.ativo_{entity}", "ativo", f"sa_{entity}")
    with postgres.connect(settings) as connection:
        if not connection.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,)).fetchone()[0]:
            raise RuntimeError(f"Já existe snapshot sa_{entity} em execução")
        connection.execute(
            "INSERT INTO raw._etl_runs (batch_id,pipeline_name,source_system,source_table,mode,status) "
            "VALUES (%s,%s,%s,%s,'SNAPSHOT','RUNNING')", (batch_id, *key))
        connection.commit()
        try:
            log("started", batch_id=batch_id, mode="SNAPSHOT")
            with mysql.connect(settings, "ativo") as reader:
                db = settings.database("ativo").database
                contract.validate_schema(reader.columns(db, f"sa_{entity}"),
                                         reader.indexes(db, f"sa_{entity}"))
                removed = load(connection, reader, batch_size, batch_id, progress, entity)
            connection.execute(
                "INSERT INTO raw._etl_watermark (pipeline_name,source_system,source_table,strategy,"
                "watermark_column,watermark_value,last_success_at) VALUES (%s,%s,%s,'snapshot',"
                "NULL,%s,clock_timestamp()) ON CONFLICT (pipeline_name,source_system,source_table) "
                "DO UPDATE SET watermark_value=EXCLUDED.watermark_value,last_success_at=clock_timestamp(),"
                "updated_at=clock_timestamp()", (*key, str(batch_id)))
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
            log("failed", batch_id=batch_id, mode="SNAPSHOT", error=type(exc).__name__,
                duration_seconds=round(monotonic()-started, 2))
            raise
        finally:
            if not connection.closed:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        log("success", batch_id=batch_id, mode="SNAPSHOT", rows_removed=removed,
            duration_seconds=round(monotonic()-started, 2), **progress)
    return batch_id

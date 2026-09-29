"""Snapshot transacional de todos os valores de opções EAV Magento."""

import json
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from psycopg import sql

from src.config.settings import ROOT
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.pipeline.text_sanitizer import replace_nul
from src.sources.magento import option_value

LOCK_ID = 7248319208
DDL = "029_create_magento_option_value_raw.sql"
TARGET = ("raw", "magento_option_value")
KEY = ("raw.magento_option_value", "magento", option_value.TABLE)


def log(event, **fields):
    print(json.dumps({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                      "source": "magento", "table": option_value.TABLE, **fields},
                     default=str), flush=True)


def load(connection, reader, batch_size, batch_id, progress):
    source_count, upper_id = reader.option_value_bounds()
    connection.execute((ROOT / "sql/postgres" / DDL).read_text(encoding="utf-8"))
    loader.prepare(connection, TARGET)
    cursor = None
    while upper_id is not None:
        rows = reader.option_value_page(batch_size=batch_size, upper_id=upper_id,
                                        cursor=cursor)
        if not rows:
            break
        cleaned, nul_count = replace_nul(rows)
        if nul_count:
            progress["nul_replacements"] = progress.get("nul_replacements", 0) + nul_count
        progress["rows_extracted"] += len(rows)
        progress["rows_loaded"] += loader.upsert(
            connection, cleaned, batch_id, TARGET,
            columns=option_value.COLUMNS, pk=option_value.PK)
        cursor = rows[-1][0]
        log("batch", batch_id=batch_id, mode="SNAPSHOT", **progress)
    if progress["rows_extracted"] != source_count:
        raise ValueError("Contagem da origem divergente; snapshot revertido")
    removed = connection.execute(
        sql.SQL("DELETE FROM {} WHERE _batch_id IS DISTINCT FROM %s")
        .format(sql.Identifier(*TARGET)), (batch_id,)).rowcount
    destination_count = connection.execute(
        sql.SQL("SELECT COUNT(*) FROM {}")
        .format(sql.Identifier(*TARGET))).fetchone()[0]
    if source_count != destination_count:
        raise ValueError("Contagem origem/destino divergente; snapshot revertido")
    log("validated", batch_id=batch_id, mode="SNAPSHOT",
        source_count=source_count, destination_count=destination_count,
        rows_removed=removed)
    return removed


def run(settings, mode="SNAPSHOT", batch_size=None):
    batch_size = settings.batch_size if batch_size is None else batch_size
    if mode != "SNAPSHOT" or batch_size <= 0:
        raise ValueError("Modo ou lote inválido para option_value")
    batch_id = uuid4()
    started = monotonic()
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with postgres.connect(settings) as connection:
        if not connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
            raise RuntimeError("Já existe snapshot option_value em execução")
        connection.execute(
            "INSERT INTO raw._etl_runs (batch_id,pipeline_name,source_system,source_table,mode,status) "
            "VALUES (%s,%s,%s,%s,'SNAPSHOT','RUNNING')", (batch_id, *KEY))
        connection.commit()
        try:
            row = connection.execute(
                "SELECT watermark_value FROM raw._etl_watermark WHERE pipeline_name=%s "
                "AND source_system=%s AND source_table=%s", KEY).fetchone()
            old = row[0] if row else None
            log("started", batch_id=batch_id, mode=mode, previous_watermark=old)
            with mysql.connect(settings, "magento") as reader:
                database = settings.database("magento").database
                option_value.validate_schema(
                    reader.columns(database, option_value.TABLE),
                    reader.indexes(database, option_value.TABLE))
                removed = load(connection, reader, batch_size, batch_id, progress)
            connection.execute(
                "INSERT INTO raw._etl_watermark (pipeline_name,source_system,source_table,strategy,"
                "watermark_column,watermark_value,last_success_at) VALUES (%s,%s,%s,'snapshot',"
                "NULL,%s,clock_timestamp()) ON CONFLICT (pipeline_name,source_system,source_table) "
                "DO UPDATE SET strategy=EXCLUDED.strategy,watermark_column=NULL,"
                "watermark_value=EXCLUDED.watermark_value,last_success_at=clock_timestamp(),"
                "updated_at=clock_timestamp()", (*KEY, str(batch_id)))
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
            log("failed", batch_id=batch_id, mode=mode, error=type(exc).__name__,
                duration_seconds=round(monotonic()-started, 2))
            raise
        finally:
            if not connection.closed:
                connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
        log("success", batch_id=batch_id, mode=mode, new_watermark=str(batch_id),
            rows_removed=removed, duration_seconds=round(monotonic()-started, 2), **progress)
    return batch_id

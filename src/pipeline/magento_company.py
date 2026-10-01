"""Empresas Magento: FULL, incremental por PK e snapshot transacional."""

import json
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from psycopg import sql

from src.config.settings import ROOT
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.pipeline.text_sanitizer import replace_nul
from src.sources.magento import company

LOCK_ID = 7248319214
DDL = "035_create_magento_company_raw.sql"
TARGET = ("raw", "magento_company")
KEY = ("raw.magento_company", "magento", company.TABLE)


def log(event, **fields):
    print(json.dumps({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                      "source": "magento", "table": company.TABLE, **fields},
                     default=str), flush=True)


def load(connection, reader, mode, batch_size, batch_id, old_id, progress):
    source_count, upper_id = reader.company_bounds(
        count_total=mode in {"FULL", "SNAPSHOT"})
    connection.execute((ROOT / "sql/postgres" / DDL).read_text(encoding="utf-8"))
    loader.prepare(connection, TARGET)
    cursor = old_id if mode == "INCREMENTAL" else None
    newest = old_id if mode == "INCREMENTAL" else None
    while upper_id is not None:
        rows = reader.company_page(batch_size=batch_size, upper_id=upper_id,
                                   cursor=cursor)
        if not rows:
            break
        cleaned, replacements = replace_nul(rows)
        if replacements:
            progress["nul_replacements"] = progress.get("nul_replacements", 0) + replacements
        progress["rows_extracted"] += len(rows)
        progress["rows_loaded"] += loader.upsert(
            connection, cleaned, batch_id, TARGET,
            columns=company.COLUMNS, pk=company.PK)
        cursor = rows[-1][0]
        newest = cursor
        log("batch", batch_id=batch_id, mode=mode, **progress)
    if mode in {"FULL", "SNAPSHOT"}:
        if progress["rows_extracted"] != source_count:
            raise ValueError("Contagem da origem divergente; carga revertida")
        if mode == "SNAPSHOT":
            progress["rows_removed"] = connection.execute(
                sql.SQL("DELETE FROM {} WHERE _batch_id IS DISTINCT FROM %s")
                .format(sql.Identifier(*TARGET)), (batch_id,)).rowcount
        destination_count = connection.execute(
            sql.SQL("SELECT COUNT(*) FROM {}")
            .format(sql.Identifier(*TARGET))).fetchone()[0]
        if source_count != destination_count:
            raise ValueError("Contagem origem/destino divergente; carga revertida")
        log("validated", batch_id=batch_id, mode=mode,
            source_count=source_count, destination_count=destination_count,
            **({"rows_removed": progress["rows_removed"]} if mode == "SNAPSHOT" else {}))
    return newest


def run(settings, mode, batch_size=None):
    batch_size = settings.batch_size if batch_size is None else batch_size
    if mode not in {"FULL", "INCREMENTAL", "SNAPSHOT"} or batch_size <= 0:
        raise ValueError("Modo ou lote inválido para empresas")
    batch_id = uuid4()
    started = monotonic()
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with postgres.connect(settings) as connection:
        if not connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
            raise RuntimeError("Já existe carga de empresas em execução")
        connection.execute(
            "INSERT INTO raw._etl_runs (batch_id,pipeline_name,source_system,source_table,mode,status) "
            "VALUES (%s,%s,%s,%s,%s,'RUNNING')", (batch_id, *KEY, mode))
        connection.commit()
        try:
            row = connection.execute(
                "SELECT watermark_value FROM raw._etl_watermark WHERE pipeline_name=%s "
                "AND source_system=%s AND source_table=%s", KEY).fetchone()
            old = int(row[0]) if row and row[0] is not None else None
            if mode == "INCREMENTAL" and old is None:
                raise ValueError("Execute FULL ou SNAPSHOT antes do incremental")
            log("started", batch_id=batch_id, mode=mode, previous_watermark=old)
            with mysql.connect(settings, "magento") as reader:
                database = settings.database("magento").database
                company.validate_schema(
                    reader.columns(database, company.TABLE),
                    reader.indexes(database, company.TABLE))
                newest = load(connection, reader, mode, batch_size, batch_id, old, progress)
            connection.execute(
                "INSERT INTO raw._etl_watermark (pipeline_name,source_system,source_table,strategy,"
                "watermark_column,watermark_value,last_success_at) VALUES (%s,%s,%s,'pk+snapshot',"
                "%s,%s,clock_timestamp()) ON CONFLICT (pipeline_name,source_system,source_table) "
                "DO UPDATE SET strategy=EXCLUDED.strategy,watermark_column=EXCLUDED.watermark_column,"
                "watermark_value=EXCLUDED.watermark_value,last_success_at=clock_timestamp(),"
                "updated_at=clock_timestamp()",
                (*KEY, company.PK, str(newest) if newest is not None else None))
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
        log("success", batch_id=batch_id, mode=mode, new_watermark=newest,
            duration_seconds=round(monotonic()-started, 2), **progress)
    return batch_id

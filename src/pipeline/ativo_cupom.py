"""Cupons Ativo: primeira carga por referências e incremental por PK crescente."""

import json
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from src.config.settings import ROOT
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.pipeline.text_sanitizer import replace_nul
from src.sources.ativo import cupom

LOCK_ID = 7248319320
DDL = "023_create_ativo_cupom_desconto_item_raw.sql"
TARGET = ("raw", "ativo_cupom_desconto_item")
KEY = ("raw.ativo_cupom_desconto_item", "ativo", cupom.TABLE)


def log(event, **fields):
    print(json.dumps({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                      "source": "ativo", "table": cupom.TABLE, **fields}, default=str), flush=True)


def _upsert(connection, rows, batch_id, progress):
    cleaned, nul_count = replace_nul(rows)
    if nul_count:
        progress["nul_replacements"] = progress.get("nul_replacements", 0) + nul_count
    progress["rows_extracted"] += len(rows)
    progress["rows_loaded"] += loader.upsert(
        connection, cleaned, batch_id, TARGET, columns=cupom.COLUMNS,
        pk=cupom.PK, source="ativo")


def load_references(connection, reader, batch_size, batch_id, upper_id, progress):
    # A tabela temporária deduplica IDs sem trazer milhões de referências para RAM.
    connection.execute("CREATE TEMP TABLE cupom_refs (id BIGINT PRIMARY KEY) ON COMMIT DROP")
    connection.execute(
        "INSERT INTO pg_temp.cupom_refs (id) "
        "SELECT DISTINCT id_cupom_desconto_item FROM raw.ativo_pedido "
        "WHERE id_cupom_desconto_item IS NOT NULL ON CONFLICT (id) DO NOTHING")
    connection.execute(
        "INSERT INTO pg_temp.cupom_refs (id) "
        "SELECT DISTINCT id_cupom_individual FROM raw.ativo_pedido_evento "
        "WHERE id_cupom_individual IS NOT NULL ON CONFLICT (id) DO NOTHING")
    reference_count = connection.execute("SELECT COUNT(*) FROM pg_temp.cupom_refs").fetchone()[0]
    progress["references_seen"] = 0
    progress["missing_source_ids"] = 0
    cursor = None
    while True:
        if cursor is None:
            ids = [row[0] for row in connection.execute(
                "SELECT id FROM pg_temp.cupom_refs ORDER BY id LIMIT %s", (batch_size,)).fetchall()]
        else:
            ids = [row[0] for row in connection.execute(
                "SELECT id FROM pg_temp.cupom_refs WHERE id > %s ORDER BY id LIMIT %s",
                (cursor, batch_size)).fetchall()]
        if not ids:
            break
        rows = reader.cupom_ids(cupom, ids, upper_id)
        progress["references_seen"] += len(ids)
        progress["missing_source_ids"] += len(ids) - len(rows)
        if rows:
            _upsert(connection, rows, batch_id, progress)
        cursor = ids[-1]
        log("batch", batch_id=batch_id, mode="RECONCILIATION", **progress)
    if progress["references_seen"] != reference_count:
        raise ValueError("Contagem de referências divergente; carga revertida")
    if progress["rows_loaded"] != progress["rows_extracted"]:
        raise ValueError("Contagem extraída/carregada divergente; carga revertida")
    log("validated", batch_id=batch_id, mode="RECONCILIATION",
        references=reference_count, matched=progress["rows_extracted"],
        missing_source_ids=progress["missing_source_ids"])


def load_incremental(connection, reader, batch_size, batch_id, old_id, upper_id, progress):
    cursor = old_id
    while upper_id is not None:
        rows = reader.snapshot_page(cupom, batch_size=batch_size,
                                    upper_id=upper_id, cursor=cursor)
        if not rows:
            break
        _upsert(connection, rows, batch_id, progress)
        cursor = rows[-1][0]
        log("batch", batch_id=batch_id, mode="INCREMENTAL", **progress)
    return cursor


def run(settings, mode, batch_size=None):
    batch_size = settings.batch_size if batch_size is None else batch_size
    if mode not in {"RECONCILIATION", "INCREMENTAL"} or batch_size <= 0:
        raise ValueError("Modo ou lote inválido para cupons")
    batch_id = uuid4()
    started = monotonic()
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with postgres.connect(settings) as connection:
        if not connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
            raise RuntimeError("Já existe carga de cupons em execução")
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
                raise ValueError("Execute reconcile --entity cupom_desconto_item antes do incremental")
            log("started", batch_id=batch_id, mode=mode,
                previous_watermark=old, initial_seed=old is None and mode == "RECONCILIATION")
            with mysql.connect(settings, "ativo") as reader:
                database = settings.database("ativo").database
                cupom.validate_schema(reader.columns(database, cupom.TABLE),
                                      reader.indexes(database, cupom.TABLE))
                _, upper_id = reader.snapshot_bounds(cupom, count_total=False)
                connection.execute((ROOT / "sql/postgres" / DDL).read_text(encoding="utf-8"))
                loader.prepare(connection, TARGET)
                if mode == "RECONCILIATION":
                    load_references(connection, reader, batch_size, batch_id,
                                    upper_id, progress)
                    newest = upper_id if old is None else old
                else:
                    newest = load_incremental(connection, reader, batch_size,
                                              batch_id, old, upper_id, progress)
            connection.execute(
                "INSERT INTO raw._etl_watermark (pipeline_name,source_system,source_table,strategy,"
                "watermark_column,watermark_value,last_success_at) VALUES (%s,%s,%s,'referenced+pk',"
                "%s,%s,clock_timestamp()) ON CONFLICT (pipeline_name,source_system,source_table) "
                "DO UPDATE SET strategy=EXCLUDED.strategy,watermark_column=EXCLUDED.watermark_column,"
                "watermark_value=EXCLUDED.watermark_value,last_success_at=clock_timestamp(),"
                "updated_at=clock_timestamp()",
                (*KEY, cupom.PK, str(newest) if newest is not None else None))
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

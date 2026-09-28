"""Cadastros Ativo: FULL, incremental por PK e reconciliação via inscrições recentes."""

import json
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from psycopg import sql

from src.config.settings import ROOT
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.pipeline.text_sanitizer import replace_nul
from src.sources.ativo import pedido, pedido_evento, usuarios

ENTITIES = {
    "usuario": (usuarios.usuario, 7248319307, "010_create_ativo_usuario_raw.sql", "id_usuario"),
    "usuario_balcao": (usuarios.usuario_balcao, 7248319308,
                       "011_create_ativo_usuario_balcao_raw.sql", "id_usuario_balcao"),
}


def log(event, entity, **fields):
    print(json.dumps({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                      "source": "ativo", "table": f"sa_{entity}", **fields}, default=str), flush=True)


def load(connection, reader, mode, batch_size, batch_id, old_id, days, progress, entity):
    contract, _, ddl, user_column = ENTITIES[entity]
    target = ("raw", f"ativo_{entity}")
    source_count, upper_id = reader.snapshot_bounds(contract, count_total=mode == "FULL")
    if mode == "RECONCILIATION":
        _, upper_event_id = reader.ativo_pedido_evento_bounds(count_total=False)
        cutoff = reader.ativo_pedido_cutoff(days)
    connection.execute((ROOT / "sql/postgres" / ddl).read_text(encoding="utf-8"))
    loader.prepare(connection, target)
    cursor = None
    newest = old_id
    if mode == "RECONCILIATION":
        missing = 0
        while upper_event_id is not None:
            refs = reader.recent_user_refs_page(user_column, cutoff, upper_event_id,
                                                batch_size, cursor=cursor)
            if not refs:
                break
            ids = sorted({row[1] for row in refs})
            rows = reader.usuario_ids(contract, ids)
            missing += len(ids) - len(rows)
            progress["rows_extracted"] += len(rows)
            if rows:
                cleaned, nul_count = replace_nul(rows)
                progress["nul_replacements"] = progress.get("nul_replacements", 0) + nul_count
                progress["rows_loaded"] += loader.upsert(
                    connection, cleaned, batch_id, target,
                    columns=contract.COLUMNS, pk=contract.PK, source="ativo")
            cursor = refs[-1][0]
            log("batch", entity, batch_id=batch_id, mode=mode,
                references_seen=len(refs), missing_source_ids=missing, **progress)
        return newest
    while upper_id is not None:
        rows = reader.snapshot_page(contract, batch_size=batch_size, upper_id=upper_id,
                                    cursor=old_id if cursor is None and mode == "INCREMENTAL" else cursor)
        if not rows:
            break
        progress["rows_extracted"] += len(rows)
        cleaned, nul_count = replace_nul(rows)
        progress["nul_replacements"] = progress.get("nul_replacements", 0) + nul_count
        progress["rows_loaded"] += loader.upsert(
            connection, cleaned, batch_id, target,
            columns=contract.COLUMNS, pk=contract.PK, source="ativo")
        cursor = rows[-1][0]
        newest = max(newest, cursor) if newest is not None else cursor
        log("batch", entity, batch_id=batch_id, mode=mode, **progress)
    if mode == "FULL":
        destination_count = connection.execute(
            sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(*target))).fetchone()[0]
        if source_count != progress["rows_extracted"] or source_count != destination_count:
            raise ValueError("Contagem origem/destino divergente; carga revertida")
        log("validated", entity, batch_id=batch_id, source_count=source_count,
            destination_count=destination_count)
    return newest


def run(settings, mode, batch_size=None, days=None, entity="usuario"):
    batch_size = settings.batch_size if batch_size is None else batch_size
    days = settings.reconciliation_days if days is None else days
    if mode not in {"FULL", "INCREMENTAL", "RECONCILIATION"} or batch_size <= 0 or days <= 0 or entity not in ENTITIES:
        raise ValueError("Modo, lote ou entidade inválidos")
    batch_id = uuid4()
    started = monotonic()
    progress = {"rows_extracted": 0, "rows_loaded": 0, "nul_replacements": 0}
    contract, lock_id, _, _ = ENTITIES[entity]
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
            if mode != "FULL" and old is None:
                raise ValueError("Execute FULL antes de incremental/reconcile")
            log("started", entity, batch_id=batch_id, mode=mode, previous_watermark=old,
                **({"days": days} if mode == "RECONCILIATION" else {}))
            with mysql.connect(settings, "ativo") as reader:
                db = settings.database("ativo").database
                contract.validate_schema(reader.columns(db, contract.TABLE),
                                         reader.indexes(db, contract.TABLE))
                if mode == "RECONCILIATION":
                    pedido.validate_schema(reader.columns(db, "sa_pedido"),
                                           reader.indexes(db, "sa_pedido"))
                    pedido_evento.validate_schema(reader.columns(db, "sa_pedido_evento"),
                                                  reader.indexes(db, "sa_pedido_evento"))
                newest = load(connection, reader, mode, batch_size, batch_id,
                              old, days, progress, entity)
            connection.execute(
                "INSERT INTO raw._etl_watermark (pipeline_name,source_system,source_table,strategy,"
                "watermark_column,watermark_value,last_success_at) VALUES (%s,%s,%s,'pk+reconciliation',"
                "%s,%s,clock_timestamp()) ON CONFLICT (pipeline_name,source_system,source_table) "
                "DO UPDATE SET watermark_column=EXCLUDED.watermark_column,"
                "watermark_value=EXCLUDED.watermark_value,last_success_at=clock_timestamp(),"
                "updated_at=clock_timestamp()", (*key, contract.PK,
                                                    str(newest) if newest is not None else None))
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
            log("failed", entity, batch_id=batch_id, mode=mode, error=type(exc).__name__,
                duration_seconds=round(monotonic()-started, 2))
            raise
        finally:
            if not connection.closed:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        log("success", entity, batch_id=batch_id, mode=mode, new_watermark=newest,
            duration_seconds=round(monotonic()-started, 2), **progress)
    return batch_id

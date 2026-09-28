"""Uma transação por carga: dados, watermark e SUCCESS são atômicos."""
import json
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from src.config.settings import ROOT
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento.sales_order import COLUMNS, validate_schema

KEY = ("raw.magento_sales_order", "magento", "sales_order")
LOCK_ID = 7248319201


def log(event, **fields):
    print(json.dumps({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                      "source": "magento", "table": "sales_order", **fields}, default=str), flush=True)


def load(connection, reader, mode, batch_size, batch_id, old, progress):
    count, upper_id, upper_time = reader.sales_order_bounds(count_total=mode == "FULL")
    connection.execute((ROOT / "sql/postgres/003_create_magento_raw.sql").read_text(encoding="utf-8"))
    loader.prepare(connection)
    newest = old
    cursor = None
    while upper_id is not None:
        rows = reader.sales_order_page(mode=mode, batch_size=batch_size, upper_id=upper_id,
                                      upper_time=upper_time, watermark=old, cursor=cursor)
        if not rows:
            break
        progress["rows_extracted"] += len(rows)
        progress["rows_loaded"] += loader.upsert(connection, rows, batch_id)
        for row in rows:
            value = row[COLUMNS.index("updated_at")]
            newest = max(newest, value) if newest else value
        last = rows[-1]
        cursor = last[0] if mode == "FULL" else (last[COLUMNS.index("updated_at")], last[0])
        log("batch", batch_id=batch_id, mode=mode, **progress)
    if mode == "FULL":
        destination = connection.execute("SELECT COUNT(*) FROM raw.magento_sales_order").fetchone()[0]
        if count != progress["rows_extracted"] or count != destination:
            raise ValueError("Contagem origem/destino divergente; carga revertida")
        log("validated", batch_id=batch_id, source_count=count, destination_count=destination)
    return newest


def run(settings, mode, batch_size=None):
    batch_size = settings.batch_size if batch_size is None else batch_size
    if mode not in {"FULL", "INCREMENTAL"} or batch_size <= 0:
        raise ValueError("Modo ou lote inválido")
    batch_id = uuid4()
    started = monotonic()
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with postgres.connect(settings) as connection:
        # Lock de sessão cobre também os commits dos registros de execução.
        if not connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
            raise RuntimeError("Já existe carga sales_order em execução")
        connection.execute(
            "INSERT INTO raw._etl_runs (batch_id,pipeline_name,source_system,source_table,mode,status) "
            "VALUES (%s,%s,%s,%s,%s,'RUNNING')", (batch_id, *KEY, mode))
        connection.commit()
        try:
            row = connection.execute(
                "SELECT watermark_value FROM raw._etl_watermark WHERE pipeline_name=%s "
                "AND source_system=%s AND source_table=%s", KEY).fetchone()
            old = datetime.fromisoformat(row[0]) if row and row[0] else None
            if mode == "INCREMENTAL" and old is None:
                raise ValueError("Execute FULL antes do incremental")
            log("started", batch_id=batch_id, mode=mode, previous_watermark=old)
            with mysql.connect(settings, "magento") as reader:
                db = settings.database("magento").database
                validate_schema(reader.columns(db, "sales_order"), reader.indexes(db, "sales_order"))
                newest = load(connection, reader, mode, batch_size, batch_id, old, progress)
            connection.execute(
                "INSERT INTO raw._etl_watermark (pipeline_name,source_system,source_table,strategy,"
                "watermark_column,watermark_value,last_success_at) VALUES (%s,%s,%s,'updated_at',"
                "'updated_at',%s,clock_timestamp()) ON CONFLICT (pipeline_name,source_system,source_table) "
                "DO UPDATE SET watermark_value=EXCLUDED.watermark_value,last_success_at=clock_timestamp(),"
                "updated_at=clock_timestamp()", (*KEY, newest.isoformat() if newest else None))
            connection.execute(
                "UPDATE raw._etl_runs SET status='SUCCESS',finished_at=clock_timestamp(),"
                "rows_extracted=%s,rows_loaded=%s WHERE batch_id=%s",
                (progress["rows_extracted"], progress["rows_loaded"], batch_id))
            connection.commit()
        except BaseException as exc:
            connection.rollback()
            # Classe somente: drivers podem incluir valores pessoais em exceções.
            connection.execute(
                "UPDATE raw._etl_runs SET status='FAILED',finished_at=clock_timestamp(),"
                "rows_extracted=%s,rows_loaded=0,error_message=%s WHERE batch_id=%s AND status='RUNNING'",
                (progress["rows_extracted"], type(exc).__name__, batch_id))
            connection.commit()
            log("failed", batch_id=batch_id, mode=mode, error=type(exc).__name__,
                duration_seconds=round(monotonic()-started, 2))
            raise
        finally:
            # Fechamento da conexão também libera o lock, mesmo após falha de rede.
            if not connection.closed:
                connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
        log("success", batch_id=batch_id, mode=mode, new_watermark=newest,
            duration_seconds=round(monotonic()-started, 2), **progress)
    return batch_id

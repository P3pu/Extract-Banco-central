"""Uma transação por carga: dados, watermark e SUCCESS são atômicos."""
import json
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4
from psycopg import sql

from src.config.settings import ROOT
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.pipeline.text_sanitizer import replace_nul
from src.sources.magento import customer, customer_address, product, sales_order, sales_order_item

ENTITIES = {
    "sales_order": (sales_order, 7248319201, "003_create_magento_raw.sql"),
    "sales_order_item": (sales_order_item, 7248319202, "003b_create_magento_sales_order_item.sql"),
    "product": (product, 7248319203, "024_create_magento_product_raw.sql"),
    "customer": (customer, 7248319209, "030_create_magento_customer_raw.sql"),
    "customer_address": (customer_address, 7248319210, "031_create_magento_customer_address_raw.sql"),
}

def log(event, **fields):
    print(json.dumps({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                      "source": "magento", "table": "sales_order", **fields}, default=str), flush=True)


def load(connection, reader, mode, batch_size, batch_id, old, progress, entity="sales_order"):
    contract, _, ddl = ENTITIES[entity]
    source_table = getattr(contract, "TABLE", entity)
    target = ("raw", f"magento_{entity}")
    if mode != "FULL":
        loader.validate_target(connection, target, contract)
    count, upper_id, upper_time = getattr(reader, f"{entity}_bounds")(count_total=mode == "FULL")
    if mode == "FULL":
        connection.execute((ROOT / "sql/postgres" / ddl).read_text(encoding="utf-8"))
    loader.prepare(connection, target)
    newest = old
    cursor = None
    while upper_id is not None:
        rows = getattr(reader, f"{entity}_page")(mode=mode, batch_size=batch_size, upper_id=upper_id,
                                      upper_time=upper_time, watermark=old, cursor=cursor)
        if not rows:
            break
        if entity in {"customer", "customer_address"}:
            rows, replacements = replace_nul(rows)
            if replacements:
                progress["nul_replacements"] = progress.get("nul_replacements", 0) + replacements
        progress["rows_extracted"] += len(rows)
        progress["rows_loaded"] += loader.upsert(connection, rows, batch_id, target,
                                                 columns=contract.COLUMNS, pk=contract.PK)
        for row in rows:
            value = row[contract.COLUMNS.index("updated_at")]
            newest = max(newest, value) if newest else value
        last = rows[-1]
        cursor = last[0] if mode == "FULL" or getattr(contract, "PAGE_BY_PK", False) else (last[contract.COLUMNS.index("updated_at")], last[0])
        log("batch", batch_id=batch_id, table=source_table, mode=mode, **progress)
    if mode == "FULL":
        destination = connection.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(*target))).fetchone()[0]
        if count != progress["rows_extracted"] or count != destination:
            raise ValueError("Contagem origem/destino divergente; carga revertida")
        log("validated", batch_id=batch_id, table=source_table,
            source_count=count, destination_count=destination)
    return newest


def run(settings, mode, batch_size=None, entity="sales_order"):
    batch_size = settings.batch_size if batch_size is None else batch_size
    if mode not in {"FULL", "INCREMENTAL"} or batch_size <= 0 or entity not in ENTITIES:
        raise ValueError("Modo ou lote inválido")
    batch_id = uuid4()
    started = monotonic()
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    contract, lock_id, _ = ENTITIES[entity]
    source_table = getattr(contract, "TABLE", entity)
    key = (f"raw.magento_{entity}", "magento", source_table)
    with postgres.connect(settings) as connection:
        # Lock de sessão cobre também os commits dos registros de execução.
        if not connection.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,)).fetchone()[0]:
            raise RuntimeError(f"Já existe carga {entity} em execução")
        connection.execute(
            "INSERT INTO raw._etl_runs (batch_id,pipeline_name,source_system,source_table,mode,status) "
            "VALUES (%s,%s,%s,%s,%s,'RUNNING')", (batch_id, *key, mode))
        connection.commit()
        try:
            row = connection.execute(
                "SELECT watermark_value FROM raw._etl_watermark WHERE pipeline_name=%s "
                "AND source_system=%s AND source_table=%s", key).fetchone()
            old = datetime.fromisoformat(row[0]) if row and row[0] else None
            if mode == "INCREMENTAL" and old is None:
                raise ValueError("Execute FULL antes do incremental")
            log("started", batch_id=batch_id, table=source_table, mode=mode, previous_watermark=old)
            with mysql.connect(settings, "magento") as reader:
                db = settings.database("magento").database
                contract.validate_schema(reader.columns(db, source_table), reader.indexes(db, source_table))
                newest = load(connection, reader, mode, batch_size, batch_id, old, progress, entity=entity)
            connection.execute(
                "INSERT INTO raw._etl_watermark (pipeline_name,source_system,source_table,strategy,"
                "watermark_column,watermark_value,last_success_at) VALUES (%s,%s,%s,'updated_at',"
                "'updated_at',%s,clock_timestamp()) ON CONFLICT (pipeline_name,source_system,source_table) "
                "DO UPDATE SET watermark_value=EXCLUDED.watermark_value,last_success_at=clock_timestamp(),"
                "updated_at=clock_timestamp()", (*key, newest.isoformat() if newest else None))
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
            log("failed", batch_id=batch_id, table=source_table, mode=mode, error=type(exc).__name__,
                duration_seconds=round(monotonic()-started, 2))
            raise
        finally:
            # Fechamento da conexão também libera o lock, mesmo após falha de rede.
            if not connection.closed:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        log("success", batch_id=batch_id, table=source_table, mode=mode, new_watermark=newest,
            duration_seconds=round(monotonic()-started, 2), **progress)
    return batch_id

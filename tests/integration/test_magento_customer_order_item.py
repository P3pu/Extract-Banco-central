import os
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import customer_order_item as contract

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_source_schema_and_pk_pages():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        contract.validate_schema(reader.columns(db, contract.TABLE),
                                 reader.indexes(db, contract.TABLE))
        count, upper = reader.customer_order_item_bounds()
        first = reader.customer_order_item_page(batch_size=5, upper_id=upper)
        second = reader.customer_order_item_page(batch_size=5, upper_id=upper,
                                                 cursor=first[-1][0])
        assert count >= 10
        assert len(first) == len(second) == 5
        assert first[-1][0] < second[0][0]


def test_copy_upsert_preserves_nullable_references():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/032_create_magento_customer_order_item_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_customer_order_item",
                                 "CREATE TEMP TABLE integration_customer_order_item"))
        target = ("pg_temp", "integration_customer_order_item")
        loader.prepare(conn, target)
        rows = [(1, None, 5), (2, 7, None)]
        assert loader.upsert(conn, rows, uuid4(), target,
                             columns=contract.COLUMNS, pk=contract.PK) == 2
        assert conn.execute("SELECT sales_order_item_item_id,customer_id FROM "
                            "pg_temp.integration_customer_order_item ORDER BY id").fetchall() == [
            (None, 5), (7, None)]

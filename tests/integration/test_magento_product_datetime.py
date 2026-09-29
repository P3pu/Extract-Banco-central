import os
from datetime import datetime
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import product_datetime as contract

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_source_schema_and_filtered_pages():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        contract.validate_schema(reader.columns(db, contract.TABLE),
                                 reader.indexes(db, contract.TABLE))
        count, upper = reader.product_datetime_bounds()
        first = reader.product_datetime_page(batch_size=5, upper_id=upper)
        second = reader.product_datetime_page(batch_size=5, upper_id=upper,
                                              cursor=first[-1][0])
    assert count >= 10
    assert len(first) == len(second) == 5
    assert first[-1][0] < second[0][0]
    assert all(row[1] == contract.ATTRIBUTE for row in [*first, *second])


def test_copy_upsert_preserves_timestamp_and_null():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/027_create_magento_product_datetime_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_product_datetime",
                                 "CREATE TEMP TABLE integration_product_datetime"))
        target = ("pg_temp", "integration_product_datetime")
        loader.prepare(conn, target)
        stamp = datetime(2026, 9, 29, 10, 20, 30)
        rows = [(1, 195, 0, 47522, stamp), (2, 195, 1, 47522, None)]
        assert loader.upsert(conn, rows, uuid4(), target,
                             columns=contract.COLUMNS, pk=contract.PK) == 2
        assert conn.execute("SELECT value FROM pg_temp.integration_product_datetime ORDER BY value_id").fetchall() == [
            (stamp,), (None,)]

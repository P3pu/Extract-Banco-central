import os
from datetime import date, datetime
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import customer

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_customer_source_schema_and_paging():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        customer.validate_schema(reader.columns(db, customer.TABLE),
                                 reader.indexes(db, customer.TABLE))
        count, upper, _ = reader.customer_bounds()
        first = reader.customer_page(mode="FULL", batch_size=5, upper_id=upper)
        second = reader.customer_page(mode="FULL", batch_size=5, upper_id=upper,
                                      cursor=first[-1][0])
        assert count >= 10
        assert len(first) == len(second) == 5
        assert first[-1][0] < second[0][0]


def test_customer_copy_upsert_preserves_nullable_and_date_text():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/030_create_magento_customer_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_customer",
                                 "CREATE TEMP TABLE integration_customer"))
        target = ("pg_temp", "integration_customer")
        loader.prepare(conn, target)
        stamp = datetime(2026, 9, 29, 10)
        row = (47522, 1, None, None, None, date(1990, 1, 2), None, None, stamp, stamp)
        assert loader.upsert(conn, [row], uuid4(), target,
                             columns=customer.COLUMNS, pk=customer.PK) == 1
        assert conn.execute("SELECT dob,firstname,taxvat FROM pg_temp.integration_customer").fetchone() == (
            "1990-01-02", None, None)
        zero_year = (47523, 1, None, None, None, "0000-09-22", None, None,
                     "0000-00-00 00:00:00", stamp)
        assert loader.upsert(conn, [zero_year], uuid4(), target,
                             columns=customer.COLUMNS, pk=customer.PK) == 1
        assert conn.execute("SELECT dob,created_at FROM pg_temp.integration_customer "
                            "WHERE entity_id=47523").fetchone() == (
            "0000-09-22", "0000-00-00 00:00:00")

import os
from datetime import datetime
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import customer_address

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_address_source_schema_and_paging():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        customer_address.validate_schema(reader.columns(db, customer_address.TABLE),
                                         reader.indexes(db, customer_address.TABLE))
        count, upper, _ = reader.customer_address_bounds()
        first = reader.customer_address_page(mode="FULL", batch_size=5, upper_id=upper)
        second = reader.customer_address_page(mode="FULL", batch_size=5, upper_id=upper,
                                              cursor=first[-1][0])
        assert count >= 10
        assert len(first) == len(second) == 5
        assert first[-1][0] < second[0][0]


def test_address_copy_upsert_preserves_nullable_parent():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/031_create_magento_customer_address_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_customer_address",
                                 "CREATE TEMP TABLE integration_customer_address"))
        target = ("pg_temp", "integration_customer_address")
        loader.prepare(conn, target)
        stamp = datetime(2026, 9, 29, 10)
        row = (47522, None, "000", "City", None, None, "Example", None, "BR", stamp, stamp)
        assert loader.upsert(conn, [row], uuid4(), target,
                             columns=customer_address.COLUMNS, pk=customer_address.PK) == 1
        assert conn.execute("SELECT parent_id,region,postcode FROM "
                            "pg_temp.integration_customer_address").fetchone() == (None, None, None)

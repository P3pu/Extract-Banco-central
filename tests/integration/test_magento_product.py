import os
from datetime import datetime
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import product

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_product_source_schema_and_paging():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        product.validate_schema(reader.columns(db, product.TABLE),
                                reader.indexes(db, product.TABLE))
        count, upper, _ = reader.product_bounds()
        first = reader.product_page(mode="FULL", batch_size=5, upper_id=upper)
        second = reader.product_page(mode="FULL", batch_size=5, upper_id=upper,
                                     cursor=first[-1][0])
        assert count >= 10
        assert len(first) == len(second) == 5
        assert first[-1][0] < second[0][0]


def test_product_copy_upsert_preserves_nullable_sku():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/024_create_magento_product_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_product",
                                 "CREATE TEMP TABLE integration_product"))
        target = ("pg_temp", "integration_product")
        loader.prepare(conn, target)
        stamp = datetime(2026, 9, 29, 10)
        row = (47522, None, "simple", 4, stamp, stamp)
        assert loader.upsert(conn, [row], uuid4(), target,
                             columns=product.COLUMNS, pk=product.PK) == 1
        assert conn.execute("SELECT sku,attribute_set_id FROM pg_temp.integration_product").fetchone() == (None, 4)

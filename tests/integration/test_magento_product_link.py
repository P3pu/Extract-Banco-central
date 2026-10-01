import os
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import product_link as contract

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_source_schema_and_pk_pages():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        contract.validate_schema(reader.columns(db, contract.TABLE),
                                 reader.indexes(db, contract.TABLE))
        count, upper = reader.product_link_bounds()
        first = reader.product_link_page(batch_size=5, upper_id=upper)
        second = reader.product_link_page(batch_size=5, upper_id=upper,
                                          cursor=first[-1][0])
        assert count >= 10
        assert len(first) == len(second) == 5
        assert first[-1][0] < second[0][0]


def test_copy_upsert_preserves_link_type():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/033_create_magento_product_link_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_product_link",
                                 "CREATE TEMP TABLE integration_product_link"))
        target = ("pg_temp", "integration_product_link")
        loader.prepare(conn, target)
        rows = [(1, 11, 12, 1), (2, 13, 14, 5)]
        assert loader.upsert(conn, rows, uuid4(), target,
                             columns=contract.COLUMNS, pk=contract.PK) == 2
        assert conn.execute("SELECT link_type_id FROM pg_temp.integration_product_link "
                            "ORDER BY link_id").fetchall() == [(1,), (5,)]

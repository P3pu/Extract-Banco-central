import os
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import company_user as contract

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_source_schema_and_pk_pages():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        contract.validate_schema(reader.columns(db, contract.TABLE),
                                 reader.indexes(db, contract.TABLE))
        count, upper = reader.company_user_bounds()
        first = reader.company_user_page(batch_size=5, upper_id=upper)
        second = reader.company_user_page(batch_size=5, upper_id=upper,
                                          cursor=first[-1][0])
        assert count >= 10
        assert len(first) == len(second) == 5
        assert first[-1][0] < second[0][0]


def test_copy_upsert_preserves_numeric_flags():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/034_create_magento_company_user_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_company_user",
                                 "CREATE TEMP TABLE integration_company_user"))
        target = ("pg_temp", "integration_company_user")
        loader.prepare(conn, target)
        rows = [(1, 11, 0, 1, 3, 4), (2, 12, 1, 0, 5, 6)]
        assert loader.upsert(conn, rows, uuid4(), target,
                             columns=contract.COLUMNS, pk=contract.PK) == 2
        assert conn.execute("SELECT is_root,status FROM pg_temp.integration_company_user "
                            "ORDER BY customer_id").fetchall() == [(0, 1), (1, 0)]

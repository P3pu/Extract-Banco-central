import os
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import company as contract

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_source_schema_and_pk_pages():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        contract.validate_schema(reader.columns(db, contract.TABLE),
                                 reader.indexes(db, contract.TABLE))
        count, upper = reader.company_bounds()
        first = reader.company_page(batch_size=5, upper_id=upper)
        second = reader.company_page(batch_size=5, upper_id=upper,
                                     cursor=first[-1][0])
        assert count >= 10
        assert len(first) == len(second) == 5
        assert first[-1][0] < second[0][0]


def test_copy_upsert_preserves_nullable_legal_name():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/035_create_magento_company_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_company",
                                 "CREATE TEMP TABLE integration_company"))
        target = ("pg_temp", "integration_company")
        loader.prepare(conn, target)
        row = (1, 11, "active", "Example", None, "example@example.test")
        assert loader.upsert(conn, [row], uuid4(), target,
                             columns=contract.COLUMNS, pk=contract.PK) == 1
        assert conn.execute("SELECT legal_name,status FROM pg_temp.integration_company").fetchone() == (
            None, "active")

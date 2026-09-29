import os
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import option_value as contract

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_source_schema_and_pk_pages():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        contract.validate_schema(reader.columns(db, contract.TABLE),
                                 reader.indexes(db, contract.TABLE))
        count, upper = reader.option_value_bounds()
        first = reader.option_value_page(batch_size=5, upper_id=upper)
        second = reader.option_value_page(batch_size=5, upper_id=upper,
                                          cursor=first[-1][0])
    assert count >= 10
    assert len(first) == len(second) == 5
    assert first[-1][0] < second[0][0]


def test_copy_upsert_preserves_option_id_and_nullable_value():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/029_create_magento_option_value_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_option_value",
                                 "CREATE TEMP TABLE integration_option_value"))
        target = ("pg_temp", "integration_option_value")
        loader.prepare(conn, target)
        rows = [(1, 50, 0, "opção ç"), (2, 50, 1, None)]
        assert loader.upsert(conn, rows, uuid4(), target,
                             columns=contract.COLUMNS, pk=contract.PK) == 2
        assert conn.execute("SELECT option_id,value FROM pg_temp.integration_option_value ORDER BY value_id").fetchall() == [
            (50, "opção ç"), (50, None)]

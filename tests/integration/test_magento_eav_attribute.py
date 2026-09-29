import os
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import eav_attribute as contract

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_source_schema_and_selected_six_attributes():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        contract.validate_schema(reader.columns(db, contract.TABLE),
                                 reader.indexes(db, contract.TABLE))
        count, upper = reader.eav_attribute_bounds()
        first = reader.eav_attribute_page(batch_size=3, upper_id=upper)
        second = reader.eav_attribute_page(batch_size=3, upper_id=upper,
                                           cursor=first[-1][0])
    assert count == 6
    assert len(first) == len(second) == 3
    assert [row[0] for row in [*first, *second]] == list(contract.ATTRIBUTES)


def test_copy_upsert_preserves_nullable_frontend_input():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/028_create_magento_eav_attribute_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_eav_attribute",
                                 "CREATE TEMP TABLE integration_eav_attribute"))
        target = ("pg_temp", "integration_eav_attribute")
        loader.prepare(conn, target)
        rows = [(73, "name", "varchar", "text"),
                (321, "event_rel_pai", "varchar", None)]
        assert loader.upsert(conn, rows, uuid4(), target,
                             columns=contract.COLUMNS, pk=contract.PK) == 2
        assert conn.execute("SELECT frontend_input FROM pg_temp.integration_eav_attribute ORDER BY attribute_id").fetchall() == [
            ("text",), (None,)]

import os
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import product_varchar as contract

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_source_schema_counts_and_known_attribute_pair():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        contract.validate_schema(reader.columns(db, contract.TABLE),
                                 reader.indexes(db, contract.TABLE))
        count, upper = reader.product_varchar_bounds()
        first = reader.product_varchar_page(batch_size=5, upper_id=upper)
        second = reader.product_varchar_page(batch_size=5, upper_id=upper,
                                             cursor=first[-1][0])
        with reader._connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM catalog_product_entity_varchar "
                "WHERE entity_id=%s AND attribute_id=%s AND value=%s",
                (47522, 321, "48158"))
            known = cursor.fetchone()[0]
    assert count >= 10 and known == 1
    assert len(first) == len(second) == 5
    assert first[-1][0] < second[0][0]
    assert all(row[1] in contract.ATTRIBUTES for row in [*first, *second])


def test_copy_upsert_preserves_literal_and_null_value():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/025_create_magento_product_varchar_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_product_varchar",
                                 "CREATE TEMP TABLE integration_product_varchar"))
        target = ("pg_temp", "integration_product_varchar")
        loader.prepare(conn, target)
        rows = [(1, 321, 0, 47522, "48158"), (2, 73, 1, 47522, None)]
        assert loader.upsert(conn, rows, uuid4(), target,
                             columns=contract.COLUMNS, pk=contract.PK) == 2
        assert conn.execute("SELECT value FROM pg_temp.integration_product_varchar ORDER BY value_id").fetchall() == [
            ("48158",), (None,)]

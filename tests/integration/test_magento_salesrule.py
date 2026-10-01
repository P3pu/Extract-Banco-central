import os
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import salesrule as contract

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_source_schema_and_pk_pages():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        contract.validate_schema(reader.columns(db, contract.TABLE),
                                 reader.indexes(db, contract.TABLE))
        count, upper = reader.salesrule_bounds()
        first = reader.salesrule_page(batch_size=5, upper_id=upper)
        second = reader.salesrule_page(batch_size=5, upper_id=upper,
                                       cursor=first[-1][0])
        assert count >= 10
        assert len(first) == len(second) == 5
        assert first[-1][0] < second[0][0]


def test_copy_upsert_preserves_zero_dates_decimal_and_long_text():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/036_create_magento_salesrule_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_salesrule",
                                 "CREATE TEMP TABLE integration_salesrule"))
        target = ("pg_temp", "integration_salesrule")
        loader.prepare(conn, target)
        values = {name: None if spec[2] else 0 for name, spec in contract.FIELDS.items()}
        values.update(rule_id=1, from_date="0000-00-00", to_date="0000-00-00",
                      conditions_serialized="x" * 70000, discount_amount=Decimal("12.3456"),
                      updated_at=datetime(2026, 10, 1, 12))
        row = tuple(values[name] for name in contract.COLUMNS)
        assert loader.upsert(conn, [row], uuid4(), target,
                             columns=contract.COLUMNS, pk=contract.PK) == 1
        assert conn.execute("SELECT from_date,to_date,discount_amount,"
                            "LENGTH(conditions_serialized),updated_at "
                            "FROM pg_temp.integration_salesrule").fetchone() == (
            "0000-00-00", "0000-00-00", Decimal("12.3456"), 70000, "2026-10-01 12:00:00")

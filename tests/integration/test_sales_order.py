"""Opt-in: SELECT de origem e testes PostgreSQL em tabelas TEMP, sem persistir dados."""
import os
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.config.settings import Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento.sales_order import COLUMNS, validate_schema

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="RUN_INTEGRATION=1 necessário")


def test_real_source_contract():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        validate_schema(reader.columns(db, "sales_order"), reader.indexes(db, "sales_order"))


def test_copy_upsert_and_rollback_in_temporary_table():
    with postgres.connect(Settings.load()) as conn:
        conn.execute("CREATE TEMP TABLE integration_sales_order (LIKE raw.magento_sales_order INCLUDING ALL) ON COMMIT DROP")
        target = ("pg_temp", "integration_sales_order")
        loader.prepare(conn, target)
        values = {"entity_id": 1, "total_item_count": 1, "created_at": datetime(2026, 1, 1),
                  "updated_at": datetime(2026, 1, 1), "grand_total": Decimal("59.1234")}
        row = tuple(values.get(name) for name in COLUMNS)
        batch_id = uuid4()
        assert loader.upsert(conn, [row], batch_id, target) == 1
        assert loader.upsert(conn, [row], batch_id, target) == 1
        assert conn.execute("SELECT count(*) FROM pg_temp.integration_sales_order").fetchone()[0] == 1
        with pytest.raises(RuntimeError):
            with conn.transaction():
                values["grand_total"] = Decimal("99.0000")
                loader.upsert(conn, [tuple(values.get(n) for n in COLUMNS)], uuid4(), target)
                raise RuntimeError("rollback simulado")
        result = conn.execute("SELECT grand_total, _source, _batch_id FROM pg_temp.integration_sales_order").fetchone()
        assert result == (Decimal("59.1234"), "magento", batch_id)

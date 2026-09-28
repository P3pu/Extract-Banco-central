import os
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.magento import sales_order_item as items

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="RUN_INTEGRATION=1 necessário")


def test_item_source_contract():
    settings = Settings.load()
    with mysql.connect(settings, "magento") as reader:
        db = settings.database("magento").database
        items.validate_schema(reader.columns(db, "sales_order_item"), reader.indexes(db, "sales_order_item"))


def test_item_copy_preserves_parent_children_text_and_rollback():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/003b_create_magento_sales_order_item.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.magento_sales_order_item", "CREATE TEMP TABLE integration_items"))
        target = ("pg_temp", "integration_items")
        loader.prepare(conn, target)
        rows = []
        for id, parent, price in ((703415, None, "59"), (703416, 703415, "49"),
                                   (703417, 703415, "10"), (703418, 703415, "0")):
            values = dict(item_id=id, order_id=1, parent_item_id=parent, price=Decimal(price),
                          base_price=Decimal(price), row_total=Decimal(price), base_row_total=Decimal(price),
                          created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
                          product_type="bundle" if parent is None else "simple",
                          ozone_customers='texto literal {não normalizar}\nç\\teste')
            rows.append(tuple(values.get(n) for n in items.COLUMNS))
        batch_id = uuid4()
        for _ in range(2):
            assert loader.upsert(conn, rows, batch_id, target, columns=items.COLUMNS, pk=items.PK) == 4
        selected = conn.execute("SELECT item_id,parent_item_id,price,ozone_customers FROM pg_temp.integration_items ORDER BY item_id").fetchall()
        assert len(selected) == 4
        assert [r[2] for r in selected] == list(map(Decimal, [59, 49, 10, 0]))
        assert all(r[3] == values["ozone_customers"] for r in selected)
        with pytest.raises(RuntimeError):
            with conn.transaction():
                loader.upsert(conn, rows, uuid4(), target, columns=items.COLUMNS, pk=items.PK)
                raise RuntimeError("rollback simulado")
        assert conn.execute("SELECT _batch_id FROM pg_temp.integration_items WHERE item_id=703415").fetchone()[0] == batch_id

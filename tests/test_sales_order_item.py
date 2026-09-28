from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.main import parser
from src.pipeline import sales_order as pipeline
from src.sources.magento import sales_order_item as items


def test_full_includes_zero_and_every_product_type():
    query, params = items.page_query("FULL", 100, 900)
    assert params == (900, 100)
    assert "item_id >" not in query
    assert "GROUP BY" not in query and "DISTINCT" not in query
    assert "product_type =" not in query
    assert "OFFSET" not in query


def test_incremental_uses_pk_cursor_not_timestamp_sort():
    stamp = datetime(2026, 9, 28, 11)
    query, params = items.page_query("INCREMENTAL", 10, 900, watermark=stamp, cursor=0)
    assert params == (900, 0, stamp-timedelta(minutes=5), 10)
    assert "item_id > %s" in query
    assert "ORDER BY item_id" in query
    assert "FORCE INDEX (PRIMARY)" in query


def test_incremental_requires_full():
    with pytest.raises(ValueError, match="FULL"):
        items.page_query("INCREMENTAL", 10, 900)


def test_schema_matches_without_updated_at_index():
    columns = [{"COLUMN_NAME": n, "COLUMN_TYPE": t[0], "IS_NULLABLE": "YES" if t[2] else "NO"}
               for n, t in items.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": "item_id", "SEQ_IN_INDEX": 1}]
    items.validate_schema(columns, indexes)
    assert items.FIELDS["ozone_customers"][1] == "TEXT"
    columns.pop()
    with pytest.raises(ValueError, match="updated_at"):
        items.validate_schema(columns, indexes)


def test_incremental_watermark_is_maximum_not_last_pk_timestamp():
    conn, reader = MagicMock(), MagicMock()
    recent, old = datetime(2026, 9, 28, 11), datetime(2026, 9, 28, 10, 58)
    rows = []
    for id, stamp in ((0, recent), (2, old)):
        row = [None] * len(items.COLUMNS)
        row[0], row[-1] = id, stamp
        rows.append(tuple(row))
    reader.sales_order_item_bounds.return_value = (None, 2, None)
    reader.sales_order_item_page.side_effect = [rows[:1], rows[1:], ()]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(pipeline.loader, "prepare"), patch.object(pipeline.loader, "upsert", return_value=1) as upsert:
        result = pipeline.load(conn, reader, "INCREMENTAL", 1, uuid4(), old, progress, "sales_order_item")
    assert result == recent
    assert reader.sales_order_item_page.call_args_list[1].kwargs["cursor"] == 0
    assert reader.sales_order_item_page.call_args_list[2].kwargs["cursor"] == 2
    assert upsert.call_args.kwargs["pk"] == "item_id"
    assert upsert.call_args.args[3] == ("raw", "magento_sales_order_item")
    assert progress == {"rows_extracted": 2, "rows_loaded": 2}


def test_entity_controls_are_isolated():
    assert pipeline.ENTITIES["sales_order"][1] != pipeline.ENTITIES["sales_order_item"][1]
    assert parser().parse_args(["full", "--entity", "sales_order_item"]).entity == "sales_order_item"
    assert parser().parse_args(["incremental"]).entity is None

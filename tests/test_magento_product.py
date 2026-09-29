from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.main import main
from src.pipeline import sales_order as pipeline
from src.sources.magento import product


def test_contract_and_pk_paging_for_full_and_incremental():
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in product.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": product.PK}]
    product.validate_schema(columns, indexes)
    assert product.FIELDS["attribute_set_id"][1] == "INTEGER"
    assert product.COLUMNS == ("entity_id", "sku", "type_id", "attribute_set_id",
                               "created_at", "updated_at")
    query, params = product.page_query("FULL", 100, 600, cursor=300)
    assert params == (600, 300, 100)
    assert "FORCE INDEX (PRIMARY)" in query and "OFFSET" not in query
    stamp = datetime(2026, 9, 29, 10)
    query, params = product.page_query("INCREMENTAL", 100, 600, watermark=stamp,
                                       cursor=300)
    assert params == (600, 300, stamp - timedelta(minutes=5), 100)
    assert "`updated_at` >= %s" in query and "ORDER BY `entity_id`" in query
    with pytest.raises(ValueError, match="FULL"):
        product.page_query("INCREMENTAL", 100, 600)
    columns[0]["COLUMN_TYPE"] = "bigint unsigned"
    with pytest.raises(ValueError, match="entity_id"):
        product.validate_schema(columns, indexes)


def test_full_count_and_incremental_pk_cursor():
    conn, reader = MagicMock(), MagicMock()
    stamp = datetime(2026, 9, 29, 10)
    row = lambda key: (key, None, "simple", 4, stamp, stamp)
    reader.product_bounds.return_value = (3, 5, None)
    reader.product_page.side_effect = [[row(1), row(3)], [row(5)], []]
    conn.execute.return_value.fetchone.return_value = (3,)
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", side_effect=lambda _, rows, *a, **k: len(rows)):
        newest = pipeline.load(conn, reader, "FULL", 2, UUID(int=1), None,
                               progress, entity="product")
    assert newest == stamp
    assert progress == {"rows_extracted": 3, "rows_loaded": 3}
    assert reader.product_page.call_args_list[1].kwargs["cursor"] == 3
    assert reader.product_page.call_args_list[2].kwargs["cursor"] == 5


def test_cli_explicit_product():
    with patch("src.main.Settings.load"), patch.object(pipeline, "run") as run:
        assert main(["full", "--source", "magento", "--entity", "product"]) == 0
        assert main(["incremental", "--source", "magento", "--entity", "product"]) == 0
    assert [call.args[1] for call in run.call_args_list] == ["FULL", "INCREMENTAL"]
    assert all(call.kwargs["entity"] == "product" for call in run.call_args_list)

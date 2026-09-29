from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.main import main
from src.pipeline import sales_order as pipeline
from src.sources.magento import customer_address


def test_contract_and_pk_paging():
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in customer_address.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": customer_address.PK}]
    customer_address.validate_schema(columns, indexes)
    assert customer_address.COLUMNS == (
        "entity_id", "parent_id", "telephone", "city", "region", "region_id",
        "street", "postcode", "country_id", "created_at", "updated_at")
    query, params = customer_address.page_query("FULL", 100, 600, cursor=300)
    assert params == (600, 300, 100)
    assert "FORCE INDEX (PRIMARY)" in query and "OFFSET" not in query
    assert "firstname" not in query and "lastname" not in query
    stamp = datetime(2026, 9, 29, 10)
    query, params = customer_address.page_query("INCREMENTAL", 100, 600,
                                                watermark=stamp, cursor=300)
    assert params == (600, 300, stamp - timedelta(minutes=5), 100)
    assert "`updated_at` >= %s" in query and "ORDER BY `entity_id`" in query
    with pytest.raises(ValueError, match="FULL"):
        customer_address.page_query("INCREMENTAL", 100, 600)
    columns[0]["COLUMN_TYPE"] = "bigint unsigned"
    with pytest.raises(ValueError, match="entity_id"):
        customer_address.validate_schema(columns, indexes)


def test_full_count_and_nul_sanitization():
    conn, reader = MagicMock(), MagicMock()
    stamp = datetime(2026, 9, 29, 10)
    row = lambda key, street: (key, None, "000", "City", None, None,
                               street, None, "BR", stamp, stamp)
    reader.customer_address_bounds.return_value = (2, 5, None)
    reader.customer_address_page.side_effect = [[row(1, "A\x00B"), row(5, "C")], []]
    conn.execute.return_value.fetchone.return_value = (2,)
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", side_effect=lambda _, rows, *a, **k: len(rows)) as upsert:
        newest = pipeline.load(conn, reader, "FULL", 2, UUID(int=1), None,
                               progress, entity="customer_address")
    assert newest == stamp
    assert progress == {"rows_extracted": 2, "rows_loaded": 2, "nul_replacements": 1}
    assert upsert.call_args.args[1][0][6] == "A\ufffdB"
    assert reader.customer_address_page.call_args_list[1].kwargs["cursor"] == 5


def test_cli_explicit_customer_address():
    with patch("src.main.Settings.load"), patch.object(pipeline, "run") as run:
        assert main(["full", "--source", "magento", "--entity", "customer_address"]) == 0
        assert main(["incremental", "--source", "magento", "--entity", "customer_address"]) == 0
    assert [call.args[1] for call in run.call_args_list] == ["FULL", "INCREMENTAL"]
    assert all(call.kwargs["entity"] == "customer_address" for call in run.call_args_list)

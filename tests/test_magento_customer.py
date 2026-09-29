from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.main import main
from src.pipeline import sales_order as pipeline
from src.sources.magento import customer


def test_contract_and_pk_paging():
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in customer.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": customer.PK}]
    customer.validate_schema(columns, indexes)
    assert customer.COLUMNS == ("entity_id", "group_id", "firstname", "lastname",
                                "email", "dob", "taxvat", "gender", "created_at", "updated_at")
    assert customer.FIELDS["dob"][1] == "TEXT"
    assert customer.FIELDS["created_at"][1] == "TEXT"
    query, params = customer.page_query("FULL", 100, 600, cursor=300)
    assert params == (600, 300, 100)
    assert "FORCE INDEX (PRIMARY)" in query and "OFFSET" not in query
    assert "password_hash" not in query and "rp_token" not in query
    stamp = datetime(2026, 9, 29, 10)
    query, params = customer.page_query("INCREMENTAL", 100, 600, watermark=stamp,
                                        cursor=300)
    assert params == (600, 300, stamp - timedelta(minutes=5), 100)
    assert "`updated_at` >= %s" in query and "ORDER BY `entity_id`" in query
    with pytest.raises(ValueError, match="FULL"):
        customer.page_query("INCREMENTAL", 100, 600)
    columns[0]["COLUMN_TYPE"] = "bigint unsigned"
    with pytest.raises(ValueError, match="entity_id"):
        customer.validate_schema(columns, indexes)


def test_full_count_and_nul_sanitization():
    conn, reader = MagicMock(), MagicMock()
    stamp = datetime(2026, 9, 29, 10)
    row = lambda key, name: (key, 1, name, None, None, None, None, None, stamp, stamp)
    reader.customer_bounds.return_value = (2, 5, None)
    reader.customer_page.side_effect = [[row(1, "a\x00b"), row(5, None)], []]
    conn.execute.return_value.fetchone.return_value = (2,)
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", side_effect=lambda _, rows, *a, **k: len(rows)) as upsert:
        newest = pipeline.load(conn, reader, "FULL", 2, UUID(int=1), None,
                               progress, entity="customer")
    assert newest == stamp
    assert progress == {"rows_extracted": 2, "rows_loaded": 2, "nul_replacements": 1}
    assert upsert.call_args.args[1][0][2] == "a\ufffdb"
    assert reader.customer_page.call_args_list[1].kwargs["cursor"] == 5


def test_cli_explicit_customer():
    with patch("src.main.Settings.load"), patch.object(pipeline, "run") as run:
        assert main(["full", "--source", "magento", "--entity", "customer"]) == 0
        assert main(["incremental", "--source", "magento", "--entity", "customer"]) == 0
    assert [call.args[1] for call in run.call_args_list] == ["FULL", "INCREMENTAL"]
    assert all(call.kwargs["entity"] == "customer" for call in run.call_args_list)

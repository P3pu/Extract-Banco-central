from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.config.settings import Settings
from src.main import main
from src.pipeline import magento_customer_order_item as pipeline
from src.sources.magento import customer_order_item as contract


def test_contract_uses_physical_pk_and_nullable_references():
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in contract.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": contract.PK}]
    contract.validate_schema(columns, indexes)
    assert contract.COLUMNS == ("id", "sales_order_item_item_id", "customer_id")
    query, params = contract.page_query(100, 1000, cursor=500)
    assert params == (1000, 500, 100)
    assert "FORCE INDEX (PRIMARY)" in query and "OFFSET" not in query
    assert "created_at" not in query and "event_product" not in query
    with pytest.raises(ValueError, match="limite"):
        contract.page_query(0, 1000)
    indexes[0]["COLUMN_NAME"] = "customer_id"
    with pytest.raises(ValueError, match="PK"):
        contract.validate_schema(columns, indexes)


def test_snapshot_validates_count_and_removes_stale_rows():
    conn, reader = MagicMock(), MagicMock()
    reader.customer_order_item_bounds.return_value = (2, 10)
    reader.customer_order_item_page.side_effect = [[(1, None, 5), (10, 7, None)], []]
    delete_result, count_result = MagicMock(), MagicMock()
    delete_result.rowcount = 1
    count_result.fetchone.return_value = (2,)
    conn.execute.side_effect = [MagicMock(), delete_result, count_result]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", return_value=2):
        newest = pipeline.load(conn, reader, "SNAPSHOT", 10, UUID(int=1), 9, progress)
    assert newest == 10
    assert progress == {"rows_extracted": 2, "rows_loaded": 2, "rows_removed": 1}
    assert reader.customer_order_item_page.call_args_list[0].kwargs["cursor"] is None
    assert reader.customer_order_item_page.call_args_list[1].kwargs["cursor"] == 10


def test_incomplete_snapshot_never_deletes():
    conn, reader = MagicMock(), MagicMock()
    reader.customer_order_item_bounds.return_value = (2, 10)
    reader.customer_order_item_page.side_effect = [[(10, 7, None)], []]
    with patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", return_value=1):
        with pytest.raises(ValueError, match="Contagem"):
            pipeline.load(conn, reader, "SNAPSHOT", 10, UUID(int=1), 9,
                          {"rows_extracted": 0, "rows_loaded": 0})
    assert not any("DELETE FROM" in str(call.args[0]) for call in conn.execute.call_args_list)


def test_incremental_uses_old_pk_and_keeps_watermark_when_empty():
    conn, reader = MagicMock(), MagicMock()
    reader.customer_order_item_bounds.return_value = (None, 100)
    reader.customer_order_item_page.return_value = []
    with patch.object(pipeline.loader, "validate_target"), patch.object(pipeline.loader, "prepare"):
        newest = pipeline.load(conn, reader, "INCREMENTAL", 10, UUID(int=1), 90,
                               {"rows_extracted": 0, "rows_loaded": 0})
    assert newest == 90
    assert reader.customer_order_item_page.call_args.kwargs["cursor"] == 90


@pytest.mark.parametrize("failure", [False, True])
def test_run_commits_watermark_only_on_success(failure):
    conn, reader = MagicMock(), MagicMock()
    conn.closed = False

    def execute(query, *args):
        result = MagicMock()
        result.fetchone.return_value = (True,) if "pg_try_advisory_lock" in str(query) else None
        return result

    conn.execute.side_effect = execute

    @contextmanager
    def pg(_):
        yield conn

    @contextmanager
    def source(*_):
        yield reader

    settings = MagicMock(spec=Settings)
    settings.batch_size = 100

    def perform(*args):
        if failure:
            raise ValueError("private payload")
        return 50

    with patch.object(pipeline.postgres, "connect", pg), \
         patch.object(pipeline.mysql, "connect", source), \
         patch.object(contract, "validate_schema"), \
         patch.object(pipeline, "load", side_effect=perform):
        if failure:
            with pytest.raises(ValueError):
                pipeline.run(settings, "FULL")
        else:
            assert isinstance(pipeline.run(settings, "FULL"), UUID)
    watermarks = [call for call in conn.execute.call_args_list
                  if "INSERT INTO raw._etl_watermark" in str(call.args[0])]
    assert bool(watermarks) == (not failure)
    assert conn.rollback.call_count == int(failure)


def test_cli_explicit_modes_and_source_guard():
    with patch("src.main.Settings.load"), patch.object(pipeline, "run") as run:
        for mode in ("full", "incremental", "snapshot"):
            assert main([mode, "--source", "magento", "--entity", "customer_order_item"]) == 0
        assert main(["snapshot", "--source", "ativo", "--entity", "customer_order_item"]) == 1
    assert [call.args[1] for call in run.call_args_list] == ["FULL", "INCREMENTAL", "SNAPSHOT"]

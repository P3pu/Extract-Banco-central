from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.config.settings import Settings
from src.main import main
from src.pipeline import magento_product_varchar as pipeline
from src.sources.magento import product_varchar as contract


def test_contract_filters_only_requested_attributes_with_pk_keyset():
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in contract.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": contract.PK, "SEQ_IN_INDEX": 1},
               {"INDEX_NAME": "attribute_idx", "COLUMN_NAME": "attribute_id", "SEQ_IN_INDEX": 1}]
    contract.validate_schema(columns, indexes)
    query, params = contract.page_query(100, 1000, cursor=500)
    assert params == (73, 321, 1000, 500, 100)
    assert "FORCE INDEX (PRIMARY)" in query and "OFFSET" not in query
    assert "`attribute_id` IN (%s, %s)" in query
    assert contract.COLUMNS == ("value_id", "attribute_id", "store_id", "entity_id", "value")
    with pytest.raises(ValueError, match="limite"):
        contract.page_query(0, 1000)
    indexes.pop()
    with pytest.raises(ValueError, match="Índice"):
        contract.validate_schema(columns, indexes)


def test_full_and_snapshot_validate_selected_count_and_delete_stale_rows():
    conn, reader = MagicMock(), MagicMock()
    reader.product_varchar_bounds.return_value = (2, 10)
    rows = [(1, 73, 0, 47522, "nome"), (10, 321, 0, 47522, "48158")]
    reader.product_varchar_page.side_effect = [rows, []]
    ddl_result, delete_result, count_result = MagicMock(), MagicMock(), MagicMock()
    delete_result.rowcount = 1
    count_result.fetchone.return_value = (2,)
    conn.execute.side_effect = [ddl_result, delete_result, count_result]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", return_value=2):
        newest = pipeline.load(conn, reader, "SNAPSHOT", 10, UUID(int=1), 9, progress)
    assert newest == 10
    assert progress == {"rows_extracted": 2, "rows_loaded": 2, "rows_removed": 1}
    assert reader.product_varchar_page.call_args_list[0].kwargs["cursor"] is None
    assert reader.product_varchar_page.call_args_list[1].kwargs["cursor"] == 10
    assert "DELETE FROM" in str(conn.execute.call_args_list[1].args[0])


def test_incremental_starts_above_old_watermark_and_preserves_it_if_empty():
    conn, reader = MagicMock(), MagicMock()
    reader.product_varchar_bounds.return_value = (None, 100)
    reader.product_varchar_page.return_value = []
    with patch.object(pipeline.loader, "prepare"):
        newest = pipeline.load(conn, reader, "INCREMENTAL", 10, UUID(int=1), 90,
                               {"rows_extracted": 0, "rows_loaded": 0})
    assert newest == 90
    assert reader.product_varchar_page.call_args.kwargs["cursor"] == 90
    assert conn.execute.call_count == 1


def test_snapshot_does_not_delete_when_extraction_is_incomplete():
    conn, reader = MagicMock(), MagicMock()
    reader.product_varchar_bounds.return_value = (2, 10)
    reader.product_varchar_page.side_effect = [[(10, 321, 0, 47522, "48158")], []]
    with patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", return_value=1):
        with pytest.raises(ValueError, match="Contagem"):
            pipeline.load(conn, reader, "SNAPSHOT", 10, UUID(int=1), 9,
                          {"rows_extracted": 0, "rows_loaded": 0})
    assert not any("DELETE FROM" in str(call.args[0]) for call in conn.execute.call_args_list)


@pytest.mark.parametrize("failure", [False, True])
def test_watermark_commits_only_after_success(failure):
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
    if not failure:
        assert watermarks[0].args[1][-1] == "50"
    assert conn.rollback.call_count == int(failure)


def test_cli_modes_are_explicit_and_source_guarded():
    with patch("src.main.Settings.load"), patch.object(pipeline, "run") as run:
        for mode in ("full", "incremental", "snapshot"):
            assert main([mode, "--source", "magento", "--entity", "product_varchar"]) == 0
        assert main(["snapshot", "--source", "ativo", "--entity", "product_varchar"]) == 1
    assert [call.args[1] for call in run.call_args_list] == ["FULL", "INCREMENTAL", "SNAPSHOT"]

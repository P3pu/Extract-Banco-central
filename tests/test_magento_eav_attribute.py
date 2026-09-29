from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.config.settings import Settings
from src.main import main, parser
from src.pipeline import magento_eav_attribute as pipeline
from src.sources.magento import eav_attribute as contract


def test_contract_and_filtered_pk_query():
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in contract.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": contract.PK}]
    contract.validate_schema(columns, indexes)
    assert contract.ATTRIBUTES == (73, 194, 195, 206, 207, 321)
    assert contract.COLUMNS == ("attribute_id", "attribute_code", "backend_type",
                                "frontend_input")
    query, params = contract.page_query(2, 321, cursor=195)
    assert params == (73, 194, 195, 206, 207, 321, 321, 195, 2)
    assert "FORCE INDEX (PRIMARY)" in query and "OFFSET" not in query
    assert "ORDER BY `attribute_id`" in query
    with pytest.raises(ValueError, match="limite"):
        contract.page_query(0, 321)
    columns[0]["COLUMN_TYPE"] = "int"
    with pytest.raises(ValueError, match="attribute_id"):
        contract.validate_schema(columns, indexes)


def test_snapshot_pages_six_rows_and_removes_stale_only_after_validation():
    conn, reader = MagicMock(), MagicMock()
    reader.eav_attribute_bounds.return_value = (6, 321)
    rows = [(id, "code", "int", "select") for id in contract.ATTRIBUTES]
    reader.eav_attribute_page.side_effect = [rows[:2], rows[2:4], rows[4:], []]
    delete_result, count_result = MagicMock(), MagicMock()
    delete_result.rowcount = 1
    count_result.fetchone.return_value = (6,)
    conn.execute.side_effect = [MagicMock(), delete_result, count_result]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", side_effect=lambda _, batch, *a, **k: len(batch)):
        removed = pipeline.load(conn, reader, 2, UUID(int=1), progress)
    assert removed == 1
    assert progress == {"rows_extracted": 6, "rows_loaded": 6}
    assert [call.kwargs["cursor"] for call in reader.eav_attribute_page.call_args_list] == [
        None, 194, 206, 321]
    assert "DELETE FROM" in str(conn.execute.call_args_list[1].args[0])


def test_incomplete_snapshot_never_deletes():
    conn, reader = MagicMock(), MagicMock()
    reader.eav_attribute_bounds.return_value = (6, 321)
    reader.eav_attribute_page.side_effect = [[(321, "event_rel_pai", "varchar", "text")], []]
    with patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", return_value=1):
        with pytest.raises(ValueError, match="Contagem"):
            pipeline.load(conn, reader, 10, UUID(int=1),
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
    settings.batch_size = 10

    def perform(*args):
        if failure:
            raise ValueError("private payload")
        return 0

    with patch.object(pipeline.postgres, "connect", pg), \
         patch.object(pipeline.mysql, "connect", source), \
         patch.object(contract, "validate_schema"), \
         patch.object(pipeline, "load", side_effect=perform):
        if failure:
            with pytest.raises(ValueError):
                pipeline.run(settings)
        else:
            assert isinstance(pipeline.run(settings), UUID)
    watermarks = [call for call in conn.execute.call_args_list
                  if "INSERT INTO raw._etl_watermark" in str(call.args[0])]
    assert bool(watermarks) == (not failure)
    assert conn.rollback.call_count == int(failure)


def test_cli_snapshot_only_and_source_guard():
    with patch("src.main.Settings.load"), patch.object(pipeline, "run") as run:
        assert main(["snapshot", "--source", "magento", "--entity", "eav_attribute"]) == 0
        assert main(["snapshot", "--source", "ativo", "--entity", "eav_attribute"]) == 1
    assert run.call_count == 1
    assert run.call_args.args[1] == "SNAPSHOT"
    with pytest.raises(SystemExit):
        parser().parse_args(["full", "--source", "magento", "--entity", "eav_attribute"])

from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.config.settings import Settings
from src.main import main, parser
from src.pipeline import magento_option_value as pipeline
from src.sources.magento import option_value as contract


def test_contract_preserves_option_id_and_pk_keyset():
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in contract.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": contract.PK}]
    contract.validate_schema(columns, indexes)
    assert contract.FIELDS["option_id"] == ("int unsigned", "BIGINT", False)
    assert contract.COLUMNS == ("value_id", "option_id", "store_id", "value")
    query, params = contract.page_query(100, 1000, cursor=500)
    assert params == (1000, 500, 100)
    assert "FORCE INDEX (PRIMARY)" in query and "OFFSET" not in query
    with pytest.raises(ValueError, match="limite"):
        contract.page_query(0, 1000)
    columns[0]["COLUMN_TYPE"] = "int"
    with pytest.raises(ValueError, match="value_id"):
        contract.validate_schema(columns, indexes)


def test_snapshot_replaces_nul_and_removes_stale_after_validation():
    conn, reader = MagicMock(), MagicMock()
    reader.option_value_bounds.return_value = (2, 10)
    reader.option_value_page.side_effect = [[(1, 50, 0, "opção\x00A"),
                                              (10, 50, 1, None)], []]
    delete_result, count_result = MagicMock(), MagicMock()
    delete_result.rowcount = 1
    count_result.fetchone.return_value = (2,)
    conn.execute.side_effect = [MagicMock(), delete_result, count_result]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", return_value=2) as upsert:
        removed = pipeline.load(conn, reader, 10, UUID(int=1), progress)
    assert removed == 1
    assert progress == {"rows_extracted": 2, "rows_loaded": 2, "nul_replacements": 1}
    assert upsert.call_args.args[1][0][3] == "opção�A"
    assert "DELETE FROM" in str(conn.execute.call_args_list[1].args[0])


def test_incomplete_snapshot_never_deletes():
    conn, reader = MagicMock(), MagicMock()
    reader.option_value_bounds.return_value = (2, 10)
    reader.option_value_page.side_effect = [[(10, 50, 0, "texto")], []]
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
    settings.batch_size = 100

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
        assert main(["snapshot", "--source", "magento", "--entity", "option_value"]) == 0
        assert main(["snapshot", "--source", "ativo", "--entity", "option_value"]) == 1
    assert run.call_count == 1
    assert run.call_args.args[1] == "SNAPSHOT"
    with pytest.raises(SystemExit):
        parser().parse_args(["full", "--source", "magento", "--entity", "option_value"])

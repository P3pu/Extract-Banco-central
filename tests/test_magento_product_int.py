from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.config.settings import Settings
from src.main import main
from src.pipeline import magento_product_int as pipeline
from src.sources.magento import product_int as contract


def test_contract_filters_three_attributes_and_preserves_nullable_int():
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in contract.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": contract.PK, "SEQ_IN_INDEX": 1},
               {"INDEX_NAME": "attribute_idx", "COLUMN_NAME": "attribute_id", "SEQ_IN_INDEX": 1}]
    contract.validate_schema(columns, indexes)
    assert contract.FIELDS["value"] == ("int", "INTEGER", True)
    query, params = contract.page_query(100, 1000, cursor=500)
    assert params == (194, 206, 207, 1000, 500, 100)
    assert "FORCE INDEX (PRIMARY)" in query and "OFFSET" not in query
    assert "`attribute_id` IN (%s, %s, %s)" in query
    with pytest.raises(ValueError, match="limite"):
        contract.page_query(0, 1000)
    indexes.pop()
    with pytest.raises(ValueError, match="Índice"):
        contract.validate_schema(columns, indexes)


def test_snapshot_validates_count_and_removes_stale_rows():
    conn, reader = MagicMock(), MagicMock()
    reader.product_int_bounds.return_value = (2, 10)
    rows = [(1, 194, 0, 47522, 0), (10, 207, 1, 47522, None)]
    reader.product_int_page.side_effect = [rows, []]
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
    assert reader.product_int_page.call_args_list[0].kwargs["cursor"] is None
    assert reader.product_int_page.call_args_list[1].kwargs["cursor"] == 10
    assert "DELETE FROM" in str(conn.execute.call_args_list[1].args[0])


def test_incomplete_snapshot_never_deletes():
    conn, reader = MagicMock(), MagicMock()
    reader.product_int_bounds.return_value = (2, 10)
    reader.product_int_page.side_effect = [[(10, 207, 0, 47522, None)], []]
    with patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", return_value=1):
        with pytest.raises(ValueError, match="Contagem"):
            pipeline.load(conn, reader, "SNAPSHOT", 10, UUID(int=1), 9,
                          {"rows_extracted": 0, "rows_loaded": 0})
    assert not any("DELETE FROM" in str(call.args[0]) for call in conn.execute.call_args_list)


def test_incremental_uses_old_id_and_keeps_watermark_when_empty():
    conn, reader = MagicMock(), MagicMock()
    reader.product_int_bounds.return_value = (None, 100)
    reader.product_int_page.return_value = []
    with patch.object(pipeline.loader, "validate_target"), patch.object(pipeline.loader, "prepare"):
        newest = pipeline.load(conn, reader, "INCREMENTAL", 10, UUID(int=1), 90,
                               {"rows_extracted": 0, "rows_loaded": 0})
    assert newest == 90
    assert reader.product_int_page.call_args.kwargs["cursor"] == 90
    assert conn.execute.call_count == 0


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
    if not failure:
        assert watermarks[0].args[1][-1] == "50"
    assert conn.rollback.call_count == int(failure)


def test_cli_modes_and_source_guard():
    with patch("src.main.Settings.load"), patch.object(pipeline, "run") as run:
        for mode in ("full", "incremental", "snapshot"):
            assert main([mode, "--source", "magento", "--entity", "product_int"]) == 0
        assert main(["snapshot", "--source", "ativo", "--entity", "product_int"]) == 1
    assert [call.args[1] for call in run.call_args_list] == ["FULL", "INCREMENTAL", "SNAPSHOT"]


def test_magento_snapshot_defaults_to_all_eav_tables():
    with patch("src.main.Settings.load"), patch("src.pipeline.magento_product_varchar.run") as varchar, \
         patch.object(pipeline, "run") as integer, \
         patch("src.pipeline.magento_product_datetime.run") as dated, \
         patch("src.pipeline.magento_eav_attribute.run") as attributes, \
         patch("src.pipeline.magento_option_value.run") as options, \
         patch("src.pipeline.magento_product_link.run") as links, \
         patch("src.pipeline.magento_company_user.run") as company_users, \
         patch("src.pipeline.magento_company.run") as companies, \
         patch("src.pipeline.magento_salesrule.run") as rules, \
         patch("src.pipeline.magento_salesrule_label.run") as labels:
        assert main(["snapshot", "--source", "magento"]) == 0
    assert varchar.call_args.args[1] == "SNAPSHOT"
    assert integer.call_args.args[1] == "SNAPSHOT"
    assert dated.call_args.args[1] == "SNAPSHOT"
    assert attributes.call_args.args[1] == "SNAPSHOT"
    assert options.call_args.args[1] == "SNAPSHOT"
    assert links.call_args.args[1] == "SNAPSHOT"
    assert company_users.call_args.args[1] == "SNAPSHOT"
    assert companies.call_args.args[1] == "SNAPSHOT"
    assert rules.call_args.args[1] == "SNAPSHOT"
    assert labels.call_args.args[1] == "SNAPSHOT"

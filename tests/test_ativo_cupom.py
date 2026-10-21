from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.config.settings import Settings
from src.main import main, parser
from src.pipeline import ativo_cupom
from src.sources.ativo import cupom


def test_coupon_contract_and_keyset_queries():
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in cupom.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": cupom.PK}]
    cupom.validate_schema(columns, indexes)
    assert cupom.FIELDS[cupom.PK][1] == "BIGINT"
    assert cupom.FIELDS["id_cupom_desconto"][1] == "BIGINT"
    assert cupom.FIELDS["fl_usado"][1] == "VARCHAR(1)"
    assert cupom.TEXT_DATES == ("dt_sistema", "dt_uso")
    query, params = cupom.page_query(100, 500, cursor=300)
    assert params == (500, 300, 100)
    assert "FORCE INDEX (PRIMARY)" in query and "OFFSET" not in query
    assert "CAST(c.`dt_sistema` AS CHAR)" in query
    assert "CAST(c.`dt_uso` AS CHAR)" in query
    ids_query, ids_params = cupom.ids_query([1, 5, 9], 500)
    assert ids_params == (1, 5, 9, 500)
    assert "IN (%s, %s, %s)" in ids_query
    columns[0]["COLUMN_TYPE"] = "int(11)"
    with pytest.raises(ValueError, match=cupom.PK):
        cupom.validate_schema(columns, indexes)


def test_reference_seed_deduplicates_ids_and_counts_missing_without_values():
    conn, reader = MagicMock(), MagicMock()
    count_result = MagicMock()
    count_result.fetchone.return_value = (3,)
    ids_result = MagicMock()
    ids_result.fetchall.return_value = [(0,), (10,), (999,)]
    empty_result = MagicMock()
    empty_result.fetchall.return_value = []
    conn.execute.side_effect = [MagicMock(), MagicMock(), MagicMock(),
                                count_result, ids_result, empty_result]
    reader.cupom_ids.return_value = [
        (0, "A", "", None, "0000-00-00 00:00:00", None, 1, None, None),
        (10, "B", "N", None, "2026-01-01 00:00:00", None, 1, None, None)]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(ativo_cupom.loader, "upsert", return_value=2):
        ativo_cupom.load_references(conn, reader, 10, "batch", 100, progress)
    assert progress == {"rows_extracted": 2, "rows_loaded": 2,
                        "references_seen": 3, "missing_source_ids": 1}
    assert reader.cupom_ids.call_args.args[1] == [0, 10, 999]


def test_incremental_uses_watermark_and_never_scans_historical_ids():
    conn, reader = MagicMock(), MagicMock()
    reader.snapshot_page.side_effect = [[(95, "A", "N", None,
                                          "2026-01-01 00:00:00", None, 1, None, None)], []]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(ativo_cupom.loader, "upsert", return_value=1):
        newest = ativo_cupom.load_incremental(conn, reader, 10, "batch",
                                               90, 100, progress)
    assert newest == 95
    assert reader.snapshot_page.call_args_list[0].kwargs["cursor"] == 90
    assert progress == {"rows_extracted": 1, "rows_loaded": 1}


@pytest.mark.parametrize(("failure", "old"),
                         [(False, None), (False, "450"), (True, None)])
def test_seed_sets_source_upper_watermark_only_after_success(failure, old):
    conn, reader = MagicMock(), MagicMock()
    conn.closed = False

    def execute(query, *args):
        result = MagicMock()
        if "pg_try_advisory_lock" in str(query):
            result.fetchone.return_value = (True,)
        elif "SELECT watermark_value" in str(query):
            result.fetchone.return_value = (old,) if old is not None else None
        return result

    conn.execute.side_effect = execute
    reader.snapshot_bounds.return_value = (None, 500)

    @contextmanager
    def pg(_):
        yield conn

    @contextmanager
    def source(*_):
        yield reader

    settings = MagicMock(spec=Settings)
    settings.batch_size = 100

    def perform(*args, **kwargs):
        if failure:
            raise ValueError("private payload")

    with patch.object(ativo_cupom.postgres, "connect", pg), \
         patch.object(ativo_cupom.mysql, "connect", source), \
         patch.object(cupom, "validate_schema"), \
         patch.object(ativo_cupom.loader, "validate_target"), patch.object(ativo_cupom.loader, "prepare"), \
         patch.object(ativo_cupom, "load_references", side_effect=perform):
        if failure:
            with pytest.raises(ValueError):
                ativo_cupom.run(settings, "RECONCILIATION")
        else:
            assert isinstance(ativo_cupom.run(settings, "RECONCILIATION"), UUID)
    watermark_calls = [call for call in conn.execute.call_args_list
                       if "INSERT INTO raw._etl_watermark" in str(call.args[0])]
    assert bool(watermark_calls) == (not failure)
    if not failure:
        assert watermark_calls[0].args[1][-1] == (old or "500")
    assert conn.rollback.call_count == int(failure)


def test_coupon_cli_seed_is_explicit_and_full_is_disallowed():
    with patch("src.main.Settings.load"), patch("src.pipeline.ativo_cupom.run") as run:
        assert main(["reconcile", "--source", "ativo", "--entity", "cupom_desconto_item"]) == 0
        assert main(["incremental", "--source", "ativo", "--entity", "cupom_desconto_item"]) == 0
        assert main(["reconcile", "--source", "ativo", "--entity", "cupom_desconto_item",
                     "--days", "30"]) == 1
    assert [call.args[1] for call in run.call_args_list] == ["RECONCILIATION", "INCREMENTAL"]
    with pytest.raises(SystemExit):
        parser().parse_args(["full", "--source", "ativo", "--entity", "cupom_desconto_item"])

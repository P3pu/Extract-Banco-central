from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.config.settings import Settings
from src.main import main
from src.pipeline import ativo_pedido as pipeline
from src.sources.ativo import pedido


def test_full_pk_keyset_includes_sparse_ids():
    query, params = pedido.page_query("FULL", 100, 121642675, cursor=5)
    assert "FORCE INDEX (PRIMARY)" in query
    assert "id_pedido > %s" in query and "id_pedido <= %s" in query
    assert "OFFSET" not in query and "GROUP BY" not in query
    assert params == (121642675, 5, 100)


def test_incremental_uses_prior_pk():
    query, params = pedido.page_query("INCREMENTAL", 10, 900, cursor=800)
    assert "dt_alteracao" in query.split("FROM")[0]
    assert "dt_alteracao >" not in query
    assert params == (900, 800, 10)


def test_reconciliation_uses_date_index_and_tie_breaker():
    cutoff = datetime(2026, 8, 29)
    stamp = datetime(2026, 9, 1)
    query, params = pedido.page_query("RECONCILIATION", 10, 900, cursor=(stamp, 15), cutoff=cutoff)
    assert "FORCE INDEX (dt_pedido)" in query
    assert "ORDER BY dt_pedido, id_pedido" in query
    assert params == (900, cutoff, stamp, stamp, 15, 10)


def test_contract_accepts_mysql_57_and_rejects_drift():
    columns = [{"COLUMN_NAME": n, "COLUMN_TYPE": t[0], "IS_NULLABLE": "YES" if t[2] else "NO"}
               for n, t in pedido.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": "id_pedido", "SEQ_IN_INDEX": 1},
               {"INDEX_NAME": "dt_pedido", "COLUMN_NAME": "dt_pedido", "SEQ_IN_INDEX": 1}]
    pedido.validate_schema(columns, indexes)
    columns[0]["COLUMN_TYPE"] = "bigint(20)"
    with pytest.raises(ValueError, match="id_pedido"):
        pedido.validate_schema(columns, indexes)
    assert pedido.FIELDS["dt_pedido"][1] == "TEXT"
    assert pedido.FIELDS["dt_alteracao"][1] == "TEXT"


def test_incremental_starts_after_watermark_and_reconcile_does_not_advance_it():
    conn, reader = MagicMock(), MagicMock()
    reader.ativo_pedido_bounds.return_value = (None, 100)
    reader.ativo_pedido_cutoff.return_value = datetime(2026, 8, 29)
    row = [None] * len(pedido.COLUMNS)
    row[0], row[pedido.COLUMNS.index("dt_pedido")] = 90, datetime(2026, 9, 1)
    reader.ativo_pedido_page.side_effect = [(tuple(row),), ()]
    with patch.object(pipeline.loader, "validate_target"), patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", return_value=1):
        progress = {"rows_extracted": 0, "rows_loaded": 0}
        assert pipeline.load(conn, reader, "RECONCILIATION", 5, uuid4(), 95, 30, progress) == 95
    assert reader.ativo_pedido_page.call_args_list[0].kwargs["cursor"] is None
    assert reader.ativo_pedido_page.call_args_list[1].kwargs["cursor"] == (datetime(2026, 9, 1), 90)
    reader.ativo_pedido_page.reset_mock(side_effect=True)
    reader.ativo_pedido_page.side_effect = [(tuple(row),), ()]
    with patch.object(pipeline.loader, "validate_target"), patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", return_value=1):
        pipeline.load(conn, reader, "INCREMENTAL", 5, uuid4(), 95, 30,
                      {"rows_extracted": 0, "rows_loaded": 0})
    assert reader.ativo_pedido_page.call_args_list[0].kwargs["cursor"] == 95


@pytest.mark.parametrize("failure", [False, True])
def test_run_atomic_watermark_and_failure(failure):
    conn, reader = MagicMock(), MagicMock()
    conn.closed = False
    conn.execute.return_value.fetchone.side_effect = [(True,), ("95",)]

    @contextmanager
    def pg(_):
        yield conn

    @contextmanager
    def source(*_):
        yield reader

    settings = MagicMock(spec=Settings)
    settings.batch_size, settings.reconciliation_days = 100, 30

    def perform(*args, **kwargs):
        args[-1].update(rows_extracted=3, rows_loaded=3)
        if failure:
            raise ValueError("private payload")
        return 95

    with patch.object(pipeline.postgres, "connect", pg), patch.object(pipeline.mysql, "connect", source), \
         patch.object(pipeline.pedido, "validate_schema"), patch.object(pipeline, "load", side_effect=perform):
        if failure:
            with pytest.raises(ValueError):
                pipeline.run(settings, "RECONCILIATION")
        else:
            assert isinstance(pipeline.run(settings, "RECONCILIATION"), UUID)
    queries = [str(c.args[0]) for c in conn.execute.call_args_list]
    assert any("INSERT INTO raw._etl_watermark" in q for q in queries) == (not failure)
    assert any("status='FAILED'" in q for q in queries) == failure
    assert conn.rollback.call_count == int(failure)


def test_cli_dispatches_ativo_and_reconcile():
    with patch("src.main.Settings.load"), patch("src.pipeline.ativo_pedido.run") as run:
        assert main(["incremental", "--source", "ativo", "--entity", "pedido"]) == 0
        assert main(["reconcile", "--source", "ativo", "--entity", "pedido", "--days", "7"]) == 0
    assert run.call_args_list[0].args[1] == "INCREMENTAL"
    assert run.call_args_list[1].args[1] == "RECONCILIATION"
    assert run.call_args_list[1].args[3] == 7

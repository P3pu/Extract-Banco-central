from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.config.settings import Settings
from src.pipeline import sales_order as pipeline
from src.sources.magento.sales_order import COLUMNS, FIELDS, page_query, validate_schema


def test_full_keyset_and_bound():
    query, params = page_query("FULL", 100, 400, None, cursor=200)
    assert "entity_id > %s" in query and "entity_id <= %s" in query
    assert "OFFSET" not in query
    assert params == (400, 200, 100)


def test_incremental_overlap_and_tie_breaker():
    stamp = datetime(2026, 9, 28, 10)
    query, params = page_query("INCREMENTAL", 2, 999, stamp, stamp, (stamp, 5))
    assert params == (999, stamp-timedelta(minutes=5), stamp, stamp, stamp, 5, 2)
    assert "ORDER BY updated_at, entity_id" in query
    assert "entity_id > %s" in query


def test_incremental_requires_full():
    with pytest.raises(ValueError, match="FULL"):
        page_query("INCREMENTAL", 100, 400, datetime.now())


def test_source_schema_drift_fails_closed():
    columns = [{"COLUMN_NAME": n, "COLUMN_TYPE": t[0], "IS_NULLABLE": "YES" if t[2] else "NO"}
               for n, t in FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": "entity_id", "SEQ_IN_INDEX": 1},
               {"INDEX_NAME": "updated", "COLUMN_NAME": "updated_at", "SEQ_IN_INDEX": 1}]
    validate_schema(columns, indexes)
    columns[0]["COLUMN_TYPE"] = "bigint unsigned"
    with pytest.raises(ValueError, match="entity_id"):
        validate_schema(columns, indexes)


def row(id, stamp):
    result = [None] * len(COLUMNS)
    result[0] = id
    result[-1] = stamp
    return tuple(result)


def test_chunking_and_watermark_does_not_regress():
    connection, reader = MagicMock(), MagicMock()
    old = datetime(2026, 9, 28)
    reader.sales_order_bounds.return_value = (3, 4, old)
    reader.sales_order_page.side_effect = [(row(1, old), row(2, old)), (row(4, old),), ()]
    connection.execute.return_value.fetchone.return_value = (3,)
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(pipeline.loader, "prepare"), patch.object(pipeline.loader, "upsert", side_effect=lambda c, r, b, *a, **k: len(r)):
        assert pipeline.load(connection, reader, "FULL", 2, UUID(int=1), old, progress) == old
    assert progress == {"rows_extracted": 3, "rows_loaded": 3}
    assert reader.sales_order_page.call_args_list[1].kwargs["cursor"] == 2
    assert reader.sales_order_page.call_args_list[2].kwargs["cursor"] == 4


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("entity", ["sales_order", "sales_order_item", "product"])
def test_atomic_success_and_rollback_without_watermark(failure, entity):
    connection, reader = MagicMock(), MagicMock()
    connection.closed = False
    connection.execute.return_value.fetchone.side_effect = [(True,), None]

    @contextmanager
    def pg(_):
        yield connection

    @contextmanager
    def source(*_):
        yield reader

    settings = MagicMock(spec=Settings)
    settings.batch_size = 100
    def perform(*args, **kwargs):
        args[-1].update(rows_extracted=12, rows_loaded=12)
        if failure:
            raise ValueError("private payload must not be logged")
        return datetime(2026, 9, 28)

    with patch.object(pipeline.postgres, "connect", pg), patch.object(pipeline.mysql, "connect", source), \
         patch.object(pipeline.ENTITIES[entity][0], "validate_schema"), patch.object(pipeline, "load", side_effect=perform):
        if failure:
            with pytest.raises(ValueError):
                pipeline.run(settings, "FULL", entity=entity)
        else:
            assert isinstance(pipeline.run(settings, "FULL", entity=entity), UUID)
    queries = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert any("INSERT INTO raw._etl_watermark" in q for q in queries) == (not failure)
    assert any("status='FAILED'" in q for q in queries) == failure
    assert connection.rollback.call_count == int(failure)
    assert connection.commit.call_count == 2
    start = next(c for c in connection.execute.call_args_list if "INSERT INTO raw._etl_runs" in str(c.args[0]))
    assert start.args[1][1:4] == (f"raw.magento_{entity}", "magento",
                                "catalog_product_entity" if entity == "product" else entity)
    if failure:
        failed = next(c for c in connection.execute.call_args_list if "status='FAILED'" in str(c.args[0]))
        assert failed.args[1][1] == "ValueError"


def test_concurrent_run_is_rejected():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (False,)
    with patch.object(pipeline.postgres, "connect") as factory:
        factory.return_value.__enter__.return_value = conn
        with pytest.raises(RuntimeError, match="execução"):
            pipeline.run(Settings.load({}), "FULL")
    conn.commit.assert_not_called()


def test_full_count_mismatch_prevents_success():
    conn, reader = MagicMock(), MagicMock()
    reader.sales_order_bounds.return_value = (1, 1, datetime(2026, 1, 1))
    reader.sales_order_page.return_value = ()
    conn.execute.return_value.fetchone.return_value = (0,)
    with patch.object(pipeline.loader, "prepare"):
        with pytest.raises(ValueError, match="Contagem"):
            pipeline.load(conn, reader, "FULL", 10, UUID(int=1), None,
                          {"rows_extracted": 0, "rows_loaded": 0})


def test_no_incremental_rows_preserves_watermark():
    conn, reader = MagicMock(), MagicMock()
    old = datetime(2026, 9, 28)
    reader.sales_order_bounds.return_value = (None, 999, old)
    reader.sales_order_page.return_value = ()
    with patch.object(pipeline.loader, "prepare"):
        result = pipeline.load(conn, reader, "INCREMENTAL", 10, UUID(int=1), old,
                               {"rows_extracted": 0, "rows_loaded": 0})
    assert result == old
    reader.sales_order_bounds.assert_called_once_with(count_total=False)

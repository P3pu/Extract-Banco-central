from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from src.automation import local_raw_core
from src.core import runner
from src.pipeline import ativo_eventos_abertos as pipeline
from src.sources.ativo import pedido, pedido_evento


def test_event_query_uses_event_index_and_pk_cursor():
    query, params = pedido_evento.by_event_query(40113, 500, cursor=9)
    assert "FORCE INDEX (id_evento)" in query
    assert "pe.id_evento = %s" in query and "pe.id_pedido_evento > %s" in query
    assert "ORDER BY pe.id_pedido_evento" in query and "OFFSET" not in query
    assert params == (40113, 9, 500)
    assert pedido_evento.by_event_query(40113, 500)[1] == (40113, 500)


@pytest.mark.parametrize("module,pk", [(pedido, "id_pedido"), (pedido_evento, "id_pedido_evento")])
def test_id_queries_are_bounded_by_pk(module, pk):
    query, params = module.by_ids_query([1, 2])
    assert pk in query and "IN (%s, %s)" in query
    assert params == (1, 2)
    with pytest.raises(ValueError):
        module.by_ids_query([])


def test_open_events_runs_daily_and_keeps_window_reconciliation_apart():
    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    conn = Mock()
    conn.execute.side_effect = [Mock(fetchone=lambda: (now, now - timedelta(hours=24)))]
    assert local_raw_core.open_events_due(conn) is True
    conn.execute.side_effect = [Mock(fetchone=lambda: (now, now - timedelta(hours=23)))]
    assert local_raw_core.open_events_due(conn) is False
    conn.execute.side_effect = [Mock(fetchone=lambda: (now, None))]
    assert local_raw_core.open_events_due(conn) is True
    assert pipeline.SOURCE_TABLE not in ("sa_pedido", "sa_pedido_evento")


def fake_connection(known=()):
    conn = Mock()
    executed = []

    def execute(query, params=None):
        executed.append((str(query), params))
        if "SELECT inscricao_id_origem FROM core.inscricao_removida_origem" in str(query):
            return Mock(fetchall=lambda: [(value,) for value in known])
        return Mock(fetchall=lambda: [])
    conn.execute.side_effect = execute
    conn.executed = executed
    return conn


def test_marks_only_ids_confirmed_absent_at_source(monkeypatch):
    writes = []
    monkeypatch.setattr(pipeline, "write_changed",
                        lambda _c, entity, rows, *_a: writes.append((entity, rows)) or len(rows))
    monkeypatch.setattr(pipeline, "raw_rows", lambda _c, ids: [(i,) for i in sorted(ids)])
    reader = Mock()
    reader.ativo_pedido_evento_by_ids.return_value = [(2, "movida para outro evento")]
    conn, journal = fake_connection(known={3}), Mock()
    result = pipeline.mark_removed(conn, reader, {1, 2, 3}, uuid4(), journal)
    assert result == {"novas": 1, "movidas": 1}
    inserts = [p for q, p in conn.executed if "INSERT INTO core.inscricao_removida_origem" in q]
    assert [p[1] for p in inserts] == [[1]]
    assert writes[0][1] == [(2, "movida para outro evento")]
    assert journal.call_args.args[3] == [(1,)]


def test_refuses_mass_removal(monkeypatch):
    monkeypatch.setattr(pipeline, "write_changed", lambda *_a: 0)
    reader = Mock()
    reader.ativo_pedido_evento_by_ids.return_value = []
    with pytest.raises(RuntimeError, match="acima do limite"):
        pipeline.mark_removed(fake_connection(), reader, set(range(pipeline.MAX_NEW_REMOVALS + 1)),
                              uuid4(), Mock())


def test_returned_id_is_unmarked_and_rederived(monkeypatch):
    monkeypatch.setattr(pipeline, "raw_rows", lambda _c, ids: [(i,) for i in sorted(ids)])
    conn, journal = fake_connection(known={5, 6}), Mock()
    assert pipeline.restore_returned(conn, {5, 7}, uuid4(), journal) == 1
    deletes = [p for q, p in conn.executed if "DELETE FROM core.inscricao_removida_origem" in q]
    assert deletes == [([5],)]
    assert journal.call_args.args[3] == [(5,)]


def test_reread_collects_by_event_and_compares_with_raw(monkeypatch):
    monkeypatch.setattr(pipeline, "open_events", lambda _c: [10])
    writes = []
    monkeypatch.setattr(pipeline, "write_changed",
                        lambda _c, entity, rows, *_a: writes.append(entity) or 1)
    captured = {}
    monkeypatch.setattr(pipeline, "mark_removed", lambda _c, _r, candidates, *_a:
                        captured.setdefault("candidates", candidates) and {"novas": 1, "movidas": 0})
    monkeypatch.setattr(pipeline, "restore_returned", lambda *_a: 0)
    index = pedido_evento.COLUMNS.index("id_pedido")
    row = [0] * len(pedido_evento.COLUMNS)
    row[0], row[index] = 100, 55
    reader = Mock()
    reader.ativo_pedido_evento_by_event.side_effect = [[tuple(row)], []]
    reader.ativo_pedido_by_ids.return_value = [(55,)]
    conn = Mock()
    conn.execute.return_value = Mock(fetchall=lambda: [(100,), (101,)])
    totals = pipeline.reread(conn, reader, uuid4(), Mock())
    assert captured["candidates"] == {101}
    assert writes == ["pedido_evento", "pedido"]
    assert totals["inscricoes"] == 1 and totals["pedidos"] == 1 and totals["removidas_novas"] == 1
    reader.ativo_pedido_by_ids.assert_called_once_with(ids=[55])


def test_removed_rule_never_counts_and_keeps_product_precedence():
    text = Path("sql/core/v1/040_inscricao_ativo.sql").read_text(encoding="utf-8")
    assert "core.inscricao_removida_origem" in text
    assert "WHEN d.removida THEN 'REMOVIDA_NA_ORIGEM'" in text
    assert text.index("THEN 'PRODUTO_NAO_INSCRICAO'") < text.index("THEN 'REMOVIDA_NA_ORIGEM'") \
        < text.index("THEN 'CANCELAMENTO_PREVALECE'")


def test_removal_migration_is_registered_after_combo_view():
    names = [path.name for path in runner.MIGRATIONS]
    assert names.index("015_inscricao_removida.sql") > names.index("009_combo_vendido.sql")

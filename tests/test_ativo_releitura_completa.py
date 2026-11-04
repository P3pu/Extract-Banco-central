from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from src.automation import core_refresh, local_raw_core
from src.pipeline import ativo_releitura_completa as pipeline


def utc(year, month, day, hour=12):
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def due_conn(now, previous):
    conn = Mock()
    conn.execute.return_value = Mock(fetchone=lambda: (now, previous))
    return conn


def test_first_run_waits_for_december(tmp_path):
    state = tmp_path / "s.json"
    assert pipeline.is_due(due_conn(utc(2026, 11, 20), None), state) is False
    assert pipeline.is_due(due_conn(utc(2026, 12, 1), None), state) is True


def test_runs_once_per_civil_month_in_brazil(tmp_path):
    state = tmp_path / "s.json"
    assert pipeline.is_due(due_conn(utc(2026, 12, 20), utc(2026, 12, 1)), state) is False
    assert pipeline.is_due(due_conn(utc(2027, 1, 1), utc(2026, 12, 1)), state) is True
    # 02:00 UTC de 1º de janeiro ainda é dezembro em São Paulo.
    assert pipeline.is_due(due_conn(utc(2027, 1, 1, 2), utc(2026, 12, 1)), state) is False


def test_interrupted_reread_is_always_due(tmp_path):
    state = tmp_path / "s.json"
    state.write_text("{}", encoding="utf-8")
    assert pipeline.is_due(due_conn(utc(2026, 11, 20), None), state) is True


def test_state_survives_on_disk(tmp_path):
    path = tmp_path / "s.json"
    assert pipeline.load_state(path) is None
    pipeline.save_state(path, {"cursor": 7})
    assert pipeline.load_state(path) == {"cursor": 7}


def reader_with(pages, upper=30):
    reader = Mock()
    reader.ativo_pedido_bounds.return_value = (None, upper)
    reader.ativo_pedido_evento_bounds.return_value = (None, upper)
    reader.ativo_pedido_page.side_effect = pages["pedido"]
    reader.ativo_pedido_evento_page.side_effect = pages["pedido_evento"]
    return reader


def wired(monkeypatch, missing=lambda *_a: set(), removed=None):
    calls = {"write": [], "missing": [], "restore": [], "removed": []}
    monkeypatch.setattr(pipeline, "write_changed",
                        lambda _c, entity, rows, *_a: calls["write"].append((entity, [r[0] for r in rows])) or 1)

    def fake_missing(_c, _entity, low, high, seen):
        calls["missing"].append((low, high, list(seen)))
        return missing(low, high)
    monkeypatch.setattr(pipeline, "missing_ids", fake_missing)
    monkeypatch.setattr(pipeline, "restore_returned",
                        lambda _c, seen, *_a: calls["restore"].append(seen) or 0)

    def fake_removed(_c, _r, absent, *_a):
        calls["removed"].append(absent)
        return removed or {"novas": len(absent), "movidas": 0}
    monkeypatch.setattr(pipeline, "mark_removed", fake_removed)
    return calls


def test_reads_both_entities_and_compares_each_page_with_raw(monkeypatch):
    calls = wired(monkeypatch, missing=lambda low, high: {25} if low == 20 else set())
    reader = reader_with({"pedido": [[(1,), (2,)], []], "pedido_evento": [[(10,), (20,)], []]})
    saved = []
    state = pipeline.new_state()
    pipeline.reread(Mock(), reader, state, lambda s: saved.append(dict(s)), uuid4(), Mock(), lambda: None)
    assert calls["write"] == [("pedido", [1, 2]), ("pedido_evento", [10, 20])]
    # Pedido não tem marca de removida; a inscrição confere a página e o que resta até o topo.
    assert calls["missing"] == [(0, 20, [10, 20]), (20, 30, [])]
    assert calls["removed"] == [{25}]
    assert state["lidas"] == 4 and state["mudaram"] == 2 and state["removidas"] == 1
    assert saved[-1]["entity"] == "pedido_evento" and saved[-1]["cursor"] == 20


def test_resumes_from_saved_cursor_without_rereading_finished_entity(monkeypatch):
    wired(monkeypatch)
    reader = reader_with({"pedido": [], "pedido_evento": [[(21,)], []]}, upper=99)
    state = {**pipeline.new_state(), "entity": "pedido_evento", "cursor": 20, "upper": 30}
    pipeline.reread(Mock(), reader, state, lambda _s: None, uuid4(), Mock(), lambda: None)
    reader.ativo_pedido_page.assert_not_called()
    reader.ativo_pedido_evento_bounds.assert_not_called()
    first = reader.ativo_pedido_evento_page.call_args_list[0].kwargs
    assert first["cursor"] == 20 and first["upper_id"] == 30 and first["mode"] == "FULL"


def test_source_failure_keeps_the_last_finished_page(monkeypatch):
    wired(monkeypatch)
    reader = reader_with({"pedido": [[(5,)], ConnectionError("tunel")], "pedido_evento": []})
    state = pipeline.new_state()
    with pytest.raises(ConnectionError):
        pipeline.reread(Mock(), reader, state, lambda _s: None, uuid4(), Mock(), lambda: None)
    assert state["entity"] == "pedido" and state["cursor"] == 5


def test_too_many_removals_stop_across_pages(monkeypatch):
    monkeypatch.setattr(pipeline, "MAX_NEW_REMOVALS", 2)
    wired(monkeypatch, missing=lambda _l, _h: {1}, removed={"novas": 2, "movidas": 0})
    reader = reader_with({"pedido": [[]], "pedido_evento": [[(10,)], [(20,)], [(30,)], []]})
    state = pipeline.new_state()
    with pytest.raises(RuntimeError, match="limite"):
        pipeline.reread(Mock(), reader, state, lambda _s: None, uuid4(), Mock(), lambda: None)
    assert state["cursor"] == 20 and state["removidas"] == 4


def test_limit_also_applies_after_the_last_page(monkeypatch):
    monkeypatch.setattr(pipeline, "MAX_NEW_REMOVALS", 2)
    wired(monkeypatch, missing=lambda low, _h: {1} if low == 10 else set(), removed={"novas": 3, "movidas": 0})
    reader = reader_with({"pedido": [[]], "pedido_evento": [[(10,)], []]})
    with pytest.raises(RuntimeError, match="limite"):
        pipeline.reread(Mock(), reader, pipeline.new_state(), lambda _s: None, uuid4(), Mock(), lambda: None)


def test_hourly_limit_stays_and_only_the_reread_passes_a_larger_one():
    many = {index * core_refresh.SPAN for index in range(core_refresh.MAX_RANGES_PER_SCOPE + 1)}
    with pytest.raises(RuntimeError):
        core_refresh.ranges(many)
    assert len(core_refresh.ranges(many, maximum=local_raw_core.FULL_REREAD_MAX_ORDER_RANGES)) == len(many)


def core_settings():
    return Mock(database=lambda _name: Mock(host="h", port=1, database="d", user="u", password="p"))


def test_core_step_clears_its_journal_only_after_success(monkeypatch, tmp_path):
    monkeypatch.setenv("BCD_STATE_DIR", str(tmp_path))
    journal = local_raw_core.ChangeJournal(local_raw_core.full_reread_paths()[1])
    journal.record_changes([("ativo", "order", 8, 8)])
    journal.close()
    from src.core import runner
    monkeypatch.setattr(runner, "connect", MagicMock())
    monkeypatch.setattr(runner, "validate_destination", Mock())
    refresh = Mock(side_effect=RuntimeError("x"))
    monkeypatch.setattr(local_raw_core, "refresh", refresh)
    failed = set()
    local_raw_core.run_full_reread_core(core_settings(), failed)
    assert failed == {"core_releitura"}
    refresh.side_effect, refresh.return_value = None, {"orders": 1, "inscriptions": 0}
    failed.clear()
    local_raw_core.run_full_reread_core(core_settings(), failed)
    assert not failed
    kwargs = refresh.call_args.kwargs
    assert kwargs["max_order_ranges"] == local_raw_core.FULL_REREAD_MAX_ORDER_RANGES
    assert refresh.call_args.args[1] == [("ativo", "order", 8, 8)]
    journal = local_raw_core.ChangeJournal(local_raw_core.full_reread_paths()[1])
    assert journal.snapshot() == []
    journal.close()


def test_core_step_does_nothing_without_a_journal(monkeypatch, tmp_path):
    monkeypatch.setenv("BCD_STATE_DIR", str(tmp_path))
    refresh = Mock()
    monkeypatch.setattr(local_raw_core, "refresh", refresh)
    local_raw_core.run_full_reread_core(core_settings(), set())
    refresh.assert_not_called()


def test_read_failure_marks_ativo_and_does_not_stop_the_cycle(monkeypatch, tmp_path):
    monkeypatch.setenv("BCD_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline, "run", Mock(side_effect=ConnectionError("tunel")))
    failed = set()
    local_raw_core.run_full_reread(Mock(), failed)
    assert failed == {"ativo"}

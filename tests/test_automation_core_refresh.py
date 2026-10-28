from unittest.mock import MagicMock, Mock

import pytest

from src.automation import core_refresh
from src.core import runner


def test_ranges_are_bounded_and_refuse_unbounded_work():
    assert core_refresh.ranges([4, 5, 100_001]) == [(0, 99_999), (100_000, 199_999)]
    with pytest.raises(RuntimeError, match="revisão de custo"):
        core_refresh.ranges(range(0, 51_000, 1000), span=1000, maximum=50)


def test_target_ranges_bound_changed_ids_and_span():
    actual = core_refresh.target_ranges([1, 2, 3, 100_001], max_ids=2)
    assert actual == [(1, 2, [1, 2]), (3, 3, [3]),
                      (100_001, 100_001, [100_001])]
    with pytest.raises(RuntimeError, match="revisão de custo"):
        core_refresh.target_ranges(range(101), max_ids=1, maximum=100)


def test_changed_order_reprocesses_existing_registrations_and_old_order():
    conn = Mock()
    def execute(query, params):
        if "inscricao_id_origem=ANY" in query:
            return Mock(fetchall=lambda: [(8,)])  # pedido antigo da inscrição 99
        if "pedido_id_origem=ANY" in query:
            return Mock(fetchall=lambda: [(99,), (100,)])
        raise AssertionError(query)
    conn.execute.side_effect = execute
    orders, inscriptions = core_refresh.affected_ids(conn, [
        ("ativo", "order", 9, 9),
        ("ativo", "inscription", 99, 9),
    ])
    assert orders["ativo"] == {8, 9}
    assert inscriptions["ativo"] == {99, 100}


def test_core_refresh_runs_orders_before_inscriptions_and_keeps_gate(monkeypatch):
    conn = MagicMock()
    conn.execute.side_effect = [Mock(fetchone=lambda: ("SELECT * FROM core.fato_inscricao WHERE false;",)),
                                Mock(fetchone=lambda: (0,))]
    monkeypatch.setattr(core_refresh, "affected_ids", lambda _conn, _pending:
                        ({"ativo": {8}}, {"ativo": {99}}))
    calls = []
    monkeypatch.setattr(core_refresh.runner, "run_range", lambda _conn, scope, low, high, _as_of,
                        cached=False, selected_ids=None:
                        calls.append((scope, low, high, selected_ids)))
    contacts = Mock(return_value={"contacts": 1, "installed": True,
                                  "enabled": True})
    monkeypatch.setattr(core_refresh, "sync_changed", contacts)
    assert core_refresh.refresh(conn, [("ativo", "order", 8, 8)]) == {
        "orders": 1, "inscriptions": 1,
    }
    assert calls == [("orders", 0, 99999, None), ("inscriptions", 99, 99, [99])]
    contacts.assert_called_once_with(conn, {"ativo": {8}}, {"ativo": {99}})


def test_multi_range_inscriptions_use_one_session_cache(monkeypatch):
    conn = MagicMock()
    conn.execute.side_effect = [Mock(fetchone=lambda: ("SELECT 1 WHERE false;",)),
                                Mock(), Mock(), Mock(fetchone=lambda: (0,))]
    monkeypatch.setattr(core_refresh, "affected_ids", lambda _conn, _pending:
                        ({"ativo": set()}, {"magento": {1, 100_001}}))
    prepare = Mock()
    run = Mock()
    monkeypatch.setattr(core_refresh.runner, "prepare_inscription_cache", prepare)
    monkeypatch.setattr(core_refresh.runner, "run_range", run)
    monkeypatch.setattr(core_refresh, "sync_changed", Mock(return_value={
        "contacts": 0, "installed": False, "enabled": False}))
    result = core_refresh.refresh(conn, [("magento", "inscription", 1, 1)])
    assert result == {"orders": 0, "inscriptions": 2}
    prepare.assert_called_once_with(conn)
    assert run.call_count == 2
    assert all(call.kwargs["cached"] is True for call in run.call_args_list)
    assert [call.kwargs["selected_ids"] for call in run.call_args_list] == [[1], [100_001]]


def test_open_indicator_gate_refuses_any_core_write(monkeypatch):
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = ("SELECT * FROM core.fato_inscricao;",)
    run = Mock()
    monkeypatch.setattr(core_refresh.runner, "run_range", run)
    with pytest.raises(RuntimeError, match="Gate"):
        core_refresh.refresh(conn, [("ativo", "order", 8, 8)])
    run.assert_not_called()


@pytest.mark.parametrize("name", (
    "030_inscricao_base.sql", "040_inscricao_ativo.sql",
    "041_inscricao_magento.sql", "050_reconciliacao_pedidos.sql",
    "060_alertas.sql",
))
def test_targeted_core_sql_combines_indexable_range_with_exact_ids(name):
    sql = runner.inscription_sql(name, cached=True, targeted=True)
    if name != "050_reconciliacao_pedidos.sql":
        assert "IN (SELECT id FROM pg_temp.core_v1_target_inscricao_ids)" in sql
        assert "BETWEEN %(id_min)s AND %(id_max)s" in sql
    else:
        assert "pg_temp.core_v1_batch_pedidos_cache" in sql


def test_target_ids_must_be_within_one_approved_range():
    conn = Mock()
    with pytest.raises(ValueError, match="fora da faixa"):
        runner.prepare_target_inscriptions(conn, 100, 199, [99])
    conn.execute.assert_not_called()

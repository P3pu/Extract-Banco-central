from datetime import datetime, timedelta, timezone
import os
import time
from unittest.mock import MagicMock, Mock

import pytest

from src.automation import local_raw_core


def test_reconciliation_is_due_every_fifteen_days():
    now = datetime(2026, 10, 26, tzinfo=timezone.utc)
    conn = Mock()
    conn.execute.side_effect = [
        Mock(fetchone=lambda: (now,)),
        Mock(fetchall=lambda: [("sa_pedido", now - timedelta(days=15)),
                               ("sa_pedido_evento", now - timedelta(days=14))]),
    ]
    assert local_raw_core.due_reconciliations(conn) == ["pedido"]


def test_raw_runs_four_incrementals_then_only_due_reconciliation(monkeypatch):
    from src.pipeline import ativo_pedido, sales_order
    calls = []
    monkeypatch.setattr(ativo_pedido, "run", lambda _settings, mode, **kwargs:
                        calls.append(("ativo", mode, kwargs["entity"], kwargs.get("days"))))
    monkeypatch.setattr(sales_order, "run", lambda _settings, mode, **kwargs:
                        calls.append(("magento", mode, kwargs["entity"], kwargs.get("days"))))
    local_raw_core.run_raw(Mock(), Mock(record_rows=Mock()), ["pedido_evento"])
    assert calls == [
        ("ativo", "INCREMENTAL", "pedido", None),
        ("ativo", "INCREMENTAL", "pedido_evento", None),
        ("magento", "INCREMENTAL", "sales_order", None),
        ("magento", "INCREMENTAL", "sales_order_item", None),
        ("ativo", "RECONCILIATION", "pedido_evento", 30),
    ]


def test_write_commands_remain_disabled_by_default(monkeypatch, capsys):
    monkeypatch.delenv("BCD_AUTOMATION_ENABLE", raising=False)
    assert local_raw_core.main(["run-once"]) == 1
    assert "AUTOMATION_FAILED RuntimeError" in capsys.readouterr().err


@pytest.mark.skipif(os.name != "nt", reason="Proteção de suspensão específica do Windows")
def test_automation_prevents_idle_sleep_only_while_running(monkeypatch):
    calls = []
    monkeypatch.setattr(local_raw_core, "windows_execution_state", calls.append)
    with local_raw_core.prevent_idle_sleep():
        assert calls == [local_raw_core.ES_CONTINUOUS |
                         local_raw_core.ES_SYSTEM_REQUIRED]
    assert calls[-1] == local_raw_core.ES_CONTINUOUS


def test_control_connection_heartbeats_and_releases_own_lock(monkeypatch):
    connection = MagicMock(closed=False)
    def execute(sql, _params=None):
        if "current_database" in sql:
            return Mock(fetchone=lambda: ("Atendimento",))
        if "pg_try_advisory_lock" in sql:
            return Mock(fetchone=lambda: (True,))
        return Mock(fetchone=lambda: (True,))
    connection.execute.side_effect = execute
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connect = Mock(return_value=connection)
    monkeypatch.setattr(local_raw_core.psycopg, "connect", connect)
    monkeypatch.setattr(local_raw_core, "CONTROL_HEARTBEAT_SECONDS", 0.01)
    with local_raw_core.control_connection(Mock()) as (_conn, assert_control):
        time.sleep(0.04)
        assert_control()
    sqls = [call.args[0] for call in connection.execute.call_args_list]
    assert "SELECT 1" in sqls
    assert any("pg_advisory_unlock" in sql for sql in sqls)
    assert "idle_session_timeout=120000" in connect.call_args.kwargs["options"]

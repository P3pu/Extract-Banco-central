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


def test_tunnel_forwards_to_original_postgres_port(monkeypatch, tmp_path):
    key_dir = tmp_path / ".ssh"
    key_dir.mkdir()
    (key_dir / "bcd_automation_ed25519").write_text("synthetic", encoding="ascii")
    monkeypatch.setattr(local_raw_core.Path, "home", lambda: tmp_path)
    original = Mock()
    original.database.return_value = Mock(host="db.example.invalid", port=59381)
    monkeypatch.setattr(local_raw_core.Settings, "load", Mock(return_value=original))
    process = Mock()
    process.poll.return_value = None
    popen = Mock(return_value=process)
    monkeypatch.setattr(local_raw_core.subprocess, "Popen", popen)
    monkeypatch.setattr(local_raw_core.socket, "create_connection",
                        Mock(return_value=MagicMock()))

    with local_raw_core.postgres_tunnel(Mock()):
        args = popen.call_args.args[0]
        assert args[args.index("-L") + 1] == "127.0.0.1:15943:127.0.0.1:59381"
        assert args[-1] == "bcd_tunnel@db.example.invalid"
    process.terminate.assert_called_once()


def test_aux_due_daily_and_reconciliation_every_fifteen_days():
    now = datetime(2026, 10, 28, tzinfo=timezone.utc)
    conn = Mock()
    conn.execute.side_effect = [
        Mock(fetchone=lambda: (now,)),
        Mock(fetchone=lambda: (now - timedelta(hours=23), now - timedelta(days=15))),
    ]
    assert local_raw_core.aux_due(conn) == (False, True)


def test_run_aux_uses_tunnel_cli_without_full(monkeypatch):
    from src import main as cli
    calls = []
    monkeypatch.setattr(cli, "main", lambda argv: calls.append(argv) or 0)
    monkeypatch.setattr(local_raw_core.os, "environ", {})
    settings = Mock()
    settings.database.return_value = Mock(host="127.0.0.1", port=15943)
    steps, failed = local_raw_core.run_aux(settings, 31)
    assert steps == len(calls) and failed == set()
    assert all(argv[0] in {"snapshot", "incremental", "reconcile"} for argv in calls)
    assert ["snapshot", "--source", "ativo"] in calls
    assert ["incremental", "--source", "magento", "--entity", "customer"] in calls
    assert ["reconcile", "--source", "ativo", "--entity", "usuario", "--days", "31"] in calls
    assert local_raw_core.os.environ["POSTGRES_PORT"] == "15943"


def test_run_aux_skips_failed_source_and_keeps_others(monkeypatch):
    from src import main as cli
    calls = []
    monkeypatch.setattr(cli, "main", lambda argv: calls.append(argv) or
                        (1 if argv[2] == "ativo" else 0))
    monkeypatch.setattr(local_raw_core.os, "environ", {})
    settings = Mock()
    settings.database.return_value = Mock(host="127.0.0.1", port=15943)
    _steps, failed = local_raw_core.run_aux(settings, 31)
    assert failed == {"ativo"}
    assert sum(argv[2] == "ativo" for argv in calls) == 1
    assert any(argv[2] == "magento" for argv in calls)


def test_raw_skips_unavailable_ativo_and_still_loads_magento(monkeypatch):
    from src.pipeline import ativo_pedido, sales_order
    calls = []

    def ativo(_settings, mode, **kwargs):
        calls.append(("ativo", kwargs["entity"]))
        raise OSError("túnel indisponível")

    monkeypatch.setattr(ativo_pedido, "run", ativo)
    monkeypatch.setattr(sales_order, "run", lambda _settings, mode, **kwargs:
                        calls.append(("magento", kwargs["entity"])))
    failed = local_raw_core.run_raw(Mock(), Mock(record_rows=Mock()), ["pedido"])
    assert failed == {"ativo"}
    assert calls == [("ativo", "pedido"), ("magento", "sales_order"),
                     ("magento", "sales_order_item")]


def test_direct_mode_uses_server_loopback_without_tunnel(monkeypatch):
    monkeypatch.setenv("BCD_DIRECT_POSTGRES", "1")
    original = Mock()
    original.env = {"POSTGRES_HOST": "127.0.0.1"}
    original.database.return_value = Mock(port=59381)
    load = Mock(side_effect=[original, "local"])
    monkeypatch.setattr(local_raw_core.Settings, "load", load)
    assert local_raw_core.local_settings() == "local"
    env = load.call_args_list[1].args[0]
    assert env["POSTGRES_HOST"] == "127.0.0.1" and env["POSTGRES_PORT"] == "59381"
    popen = Mock()
    monkeypatch.setattr(local_raw_core.subprocess, "Popen", popen)
    with local_raw_core.postgres_access(Mock()):
        pass
    popen.assert_not_called()


def test_state_dir_overrides_windows_journal_path(monkeypatch, tmp_path):
    monkeypatch.setenv("BCD_STATE_DIR", str(tmp_path))
    assert local_raw_core.journal_path() == tmp_path / "pending.sqlite"

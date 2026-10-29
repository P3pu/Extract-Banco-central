from datetime import date
from unittest.mock import Mock

import pytest

from src.automation import core_recovery


def test_recovery_runs_ativo_then_magento_with_production_gate(monkeypatch):
    calls = []
    aux = Mock(return_value=(33, set()))
    monkeypatch.setattr(core_recovery.local_raw_core, "run_aux", aux)
    monkeypatch.setattr(core_recovery.verified_bulk, "main",
                        lambda argv: calls.append(argv) or 0)
    conn = Mock()
    conn.execute.return_value = Mock(fetchone=lambda: (0,))
    settings = Mock()
    settings.database.return_value = Mock(host="127.0.0.1", port=15943,
                                          database="Atendimento", user="u",
                                          password="p")
    assert core_recovery.run(settings, lambda: None, conn, date(2026, 10, 28)) == 0
    assert [argv[1] for argv in calls] == ["19400000", "0"]
    assert "--ativo-only" in calls[0] and "--ativo-only" not in calls[1]
    assert all("--approve-production" in argv for argv in calls)
    assert all("2026-10-28" in argv for argv in calls)
    assert aux.call_args.args[1] == 31


def test_recovery_resumes_at_first_pending_chunk(monkeypatch):
    calls = []
    monkeypatch.setattr(core_recovery.local_raw_core, "run_aux", Mock(return_value=(27, set())))
    monkeypatch.setattr(core_recovery.verified_bulk, "main",
                        lambda argv: calls.append(argv) or 0)
    pending = {"ativo": None, "magento": 1540001}

    def execute(sql, params=None):
        if params:
            return Mock(fetchone=lambda: (pending[params[0]],))
        return Mock(fetchone=lambda: (0,))

    conn = Mock()
    conn.execute.side_effect = execute
    settings = Mock()
    settings.database.return_value = Mock(host="127.0.0.1", port=1,
                                          database="Atendimento", user="u",
                                          password="p")
    core_recovery.run(settings, lambda: None, conn, date(2026, 10, 29))
    assert [argv[1] for argv in calls] == ["1540000"]
    assert "--ativo-only" not in calls[0]


def test_recovery_stops_on_failed_range(monkeypatch):
    monkeypatch.setattr(core_recovery.local_raw_core, "run_aux", Mock(return_value=(1, set())))
    monkeypatch.setattr(core_recovery.verified_bulk, "main", Mock(return_value=1))
    conn = Mock()
    conn.execute.return_value = Mock(fetchone=lambda: (5,))
    settings = Mock()
    settings.database.return_value = Mock(host="127.0.0.1", port=1,
                                          database="Atendimento", user="u",
                                          password="p")
    with pytest.raises(RuntimeError):
        core_recovery.run(settings, lambda: None, conn, date(2026, 10, 28))


def test_recovery_requires_automation_gate(monkeypatch, capsys):
    monkeypatch.delenv("BCD_AUTOMATION_ENABLE", raising=False)
    assert core_recovery.main([]) == 1
    assert "RECOVERY_FAILED RuntimeError" in capsys.readouterr().err


def test_recovery_stops_when_registry_refresh_fails(monkeypatch):
    monkeypatch.setattr(core_recovery.local_raw_core, "run_aux",
                        Mock(return_value=(27, {"ativo"})))
    bulk = Mock(return_value=0)
    monkeypatch.setattr(core_recovery.verified_bulk, "main", bulk)
    with pytest.raises(RuntimeError):
        core_recovery.run(Mock(), lambda: None, Mock(), date(2026, 10, 28))
    bulk.assert_not_called()

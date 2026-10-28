from unittest.mock import MagicMock, Mock

import pytest

from src.core import event_unification


def write(tmp_path, body):
    path = tmp_path / "pares.csv"
    path.write_text(body, encoding="utf-8")
    return path


def test_versioned_decisions_are_unique_and_complete():
    decisions = event_unification.load_decisions(event_unification.DEFAULT_FILE)
    assert len(decisions) == 482
    assert len({magento for _sku, magento, _ativo in decisions}) == 482


def test_rejects_repeated_magento_event(tmp_path):
    path = write(tmp_path, "sku,magento_evento_id,ativo_evento_id,motivo\n"
                           "A,1,2,x\nA,1,3,x\n")
    with pytest.raises(ValueError):
        event_unification.load_decisions(path)


def test_rejects_missing_sku(tmp_path):
    path = write(tmp_path, "sku,magento_evento_id,ativo_evento_id,motivo\n,1,2,x\n")
    with pytest.raises(ValueError):
        event_unification.load_decisions(path)


def test_invalid_pair_aborts_before_writing():
    conn = MagicMock()
    conn.execute.return_value = Mock(fetchall=lambda: [(1, None), (2, "SKU_DIVERGENTE")])
    with pytest.raises(RuntimeError):
        event_unification.validate(conn)


def test_apply_and_revert_require_production_approval(capsys):
    assert event_unification.main(["apply"]) == 1
    assert "EVENT_UNIFY_FAILED RuntimeError" in capsys.readouterr().err


def test_apply_only_marks_manual_links_and_keeps_origin_guard():
    conn = MagicMock()
    conn.execute.return_value = Mock(rowcount=3)
    assert event_unification.apply(conn) == (3, 3)
    sql = conn.execute.call_args_list[0].args[0]
    assert "criterio_vinculo='MANUAL_VALIDADO'" in sql
    assert "s.origem='magento'" in sql

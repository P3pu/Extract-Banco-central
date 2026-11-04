from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, Mock

from psycopg import Rollback

from src.automation import local_raw_core
from src.automation.change_journal import ChangeJournal
from src.core import event_sync, person_dimension, runner

D1, D2 = date(2026, 11, 8), date(2026, 11, 15)


def test_single_ativo_event_unifies_even_with_another_date():
    decisions, review = event_sync.build_decisions([("CDE26MN4", 61086, 40144, D1, 525)], {})
    assert decisions == [("CDE26MN4", 61086, 40144, [])] and review == []


def test_variants_on_same_date_join_the_event_with_most_registrations():
    rows = [("BLU26RJ1", 7, 10, D1, 0), ("BLU26RJ1", 7, 11, D1, 2930)]
    assert event_sync.build_decisions(rows, {})[0] == [("BLU26RJ1", 7, 11, [10])]


def test_tie_is_stable():
    rows = [("S", 7, 11, D1, 0), ("S", 7, 10, D1, 0)]
    assert event_sync.build_decisions(rows, {})[0] == [("S", 7, 10, [11])]


def test_other_dates_without_curation_stay_out_for_review():
    rows = [("BBR25SLP1", 7, 10, D1, 2237), ("BBR25SLP1", 7, 11, D2, 2568)]
    assert event_sync.build_decisions(rows, {}) == ([], ["BBR25SLP1"])


def test_curation_keeps_only_the_right_city():
    rows = [("BBR25SLP1", 7, 10, D1, 2237), ("BBR25SLP1", 7, 11, D2, 2568), ("BBR25SLP1", 7, 12, D1, 0)]
    decisions, review = event_sync.build_decisions(rows, {"BBR25SLP1": {10, 12}})
    assert decisions == [("BBR25SLP1", 7, 10, [12])] and review == []


def test_shipped_curation_leaves_other_cities_out():
    curated = event_sync.load_curation()
    assert 39797 not in curated["BBR25SLP1"]  # Rio de Janeiro
    assert 39794 not in curated["BBR25CGP1"]  # São Paulo
    assert curated["BLR0124SJP1"] == {39506}  # sem Natal
    assert 39447 not in curated["EVCDE24SV2"]  # treino de Fortaleza


def test_magento_date_wins_only_on_unified_keys():
    assert "s.evento_key<>m.evento_key" in event_sync.MAGENTO_DATE_WINS
    assert "NOT EXISTS" in event_sync.REFRESH_ATIVO


def test_oversized_daily_run_is_rolled_back(monkeypatch):
    conn = MagicMock()
    conn.transaction.return_value.__exit__.side_effect = lambda kind, *_a: kind is Rollback
    conn.execute.return_value = Mock(fetchall=lambda: [])
    monkeypatch.setattr(event_sync, "refresh_dates", lambda _c: {1})
    monkeypatch.setattr(event_sync, "affected", lambda _c, _k: [("ativo", "inscription", i, i) for i in range(3)])
    # Desfeito, nada pode ir para o diário.
    assert event_sync.sync(conn, curated={}, maximum=2) == []
    assert len(event_sync.sync(conn, curated={}, maximum=None)) == 3


def test_ativo_date_follows_event_dimension():
    text = Path("sql/core/v1/030_inscricao_base.sql").read_text(encoding="utf-8")
    assert "COALESCE(de.data_evento,core.try_date(i.data_evento)) data_evento" in text


def test_flag_view_is_a_tail_migration_and_names_every_reason():
    assert runner.MIGRATIONS[-1].name == "017_inscricao_fora_kpi_pessoas.sql"
    text = runner.MIGRATIONS[-1].read_text(encoding="utf-8")
    for reason in ("CPF_INVALIDO", "SEM_CPF", "CLIENTE_AMBIGUO", "SEM_CLIENTE",
                   "CLIENTE_NAO_CARREGADO", "PENDENTE_VINCULO", "SEM_PARTICIPANTE",
                   "PARTICIPANTE_SEM_CADASTRO"):
        assert reason in text
    assert "flag_fora_kpi_pessoas" in text and "não aparece nos KPIs de pessoas" in text


def test_journal_records_given_changes(tmp_path):
    journal = ChangeJournal(tmp_path / "p.sqlite")
    journal.record_changes([("magento", "inscription", 5, 9), ("magento", "inscription", 5, 9)])
    assert journal.snapshot() == [("magento", "inscription", 5, 9)]
    journal.close()


def test_relink_syncs_each_origin_in_chunks(monkeypatch):
    conn = MagicMock()
    conn.execute.side_effect = [Mock(fetchall=lambda: [(1,), (2,), (3,)]), Mock(fetchall=lambda: [(9,)])]
    calls = []
    monkeypatch.setattr(person_dimension, "sync_changed",
                        lambda _c, orders, inscriptions: calls.append(inscriptions))
    result = person_dimension.relink_missing(conn, date(2026, 1, 1), maximum=10, chunk=2)
    assert calls == [{"magento": {1, 2}}, {"magento": {3}}, {"ativo": {9}}]
    assert result == {"magento": 3, "ativo": 1}


def test_daily_step_failure_does_not_stop_the_cycle(monkeypatch):
    failed = set()
    monkeypatch.setattr(local_raw_core, "_daily_core", Mock(side_effect=RuntimeError("x")))
    local_raw_core.run_daily_core(Mock(), Mock(), failed)
    assert failed == {"core_diario"}


def test_empty_date_is_not_a_different_date():
    rows = [("NRU25SP1", 7, 10, None, 0), ("NRU25SP1", 7, 11, D1, 4854)]
    assert event_sync.build_decisions(rows, {})[0] == [("NRU25SP1", 7, 11, [10])]

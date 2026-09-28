from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.config.settings import Settings
from src.main import main
from src.pipeline import ativo_financeiro
from src.sources.ativo import financeiro


@pytest.mark.parametrize("contract", [financeiro.pedido_pagamento, financeiro.transacao])
def test_contract_schema_and_keyset(contract):
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in contract.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": contract.PK, "SEQ_IN_INDEX": 1}]
    indexes += [{"INDEX_NAME": (contract.INDEX_NAMES or {}).get(name, name),
                 "COLUMN_NAME": name, "SEQ_IN_INDEX": 1}
                for name in (contract.RECON_DATES or ("id_pedido_pagamento",))]
    contract.validate_schema(columns, indexes)
    query, params = contract.page_query(100, 500, cursor=300)
    assert params == (500, 300, 100)
    assert f"t.`{contract.PK}` > %s" in query
    assert "FORCE INDEX (PRIMARY)" in query and "OFFSET" not in query
    columns[0]["COLUMN_TYPE"] = "bigint(20)"
    with pytest.raises(ValueError, match=contract.PK):
        contract.validate_schema(columns, indexes)
    columns[0]["COLUMN_TYPE"] = contract.FIELDS[contract.PK][0]
    with pytest.raises(ValueError, match="Índice"):
        contract.validate_schema(columns, indexes[:1])


def test_payment_zero_date_text_and_indexed_reconciliation():
    contract = financeiro.pedido_pagamento
    assert contract.FIELDS["dt_pagamento"][1] == "TEXT"
    query, params = contract.reconcile_page_query(
        "2026-09-01", 900, 100, cursor=("2026-09-02 00:00:00", 123),
        date_column="dt_pagamento")
    assert "CAST(t.`dt_pagamento` AS CHAR)" in query
    assert "FORCE INDEX (`dt_pagamento`)" in query
    assert "ORDER BY t.`dt_pagamento`, t.`id_pedido_pagamento`" in query
    assert params == ("2026-09-01", 900, "2026-09-02 00:00:00",
                      "2026-09-02 00:00:00", 123, 100)
    register_query, _ = contract.reconcile_page_query(
        "2026-09-01", 900, 100, date_column="dt_registro")
    assert "FORCE INDEX (`idx_dt_registro`)" in register_query
    with pytest.raises(ValueError, match="Coluna"):
        contract.reconcile_page_query("2026-09-01", 900, 100, date_column="fl_status")


def test_transaction_reconciliation_is_explicit_pk_scan():
    query, params = financeiro.transacao.reconcile_page_query("2026-09-01", 900, 100,
                                                                cursor=300)
    assert "FORCE INDEX (PRIMARY)" in query
    assert "dt_cadastro` >= %s OR t.`dt_cancelamento_transacao` >= %s" in query
    assert params == (900, "2026-09-01", "2026-09-01", 300, 100)


def test_payment_reconciliation_runs_both_indexed_windows_without_advancing_watermark():
    conn, reader = MagicMock(), MagicMock()
    reader.snapshot_bounds.return_value = (None, 900)
    reader.ativo_pedido_cutoff.return_value = "2026-09-01"
    reader.financeiro_reconcile_page.side_effect = [
        [(123, 1, 2, "CONFIRMADO", "2026-09-02", "2026-09-03")], [],
        [(123, 1, 2, "CONFIRMADO", "2026-09-02", "2026-09-03")], []]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(ativo_financeiro.loader, "prepare"), \
         patch.object(ativo_financeiro.loader, "upsert", return_value=1) as upsert:
        newest = ativo_financeiro.load(conn, reader, "RECONCILIATION", 100,
                                      uuid4(), 99, 30, progress, "pedido_pagamento")
    assert newest == 99
    assert progress == {"rows_extracted": 2, "rows_loaded": 2}
    assert upsert.call_count == 2
    assert [call.kwargs["date_column"] for call in reader.financeiro_reconcile_page.call_args_list] == [
        "dt_registro", "dt_registro", "dt_pagamento", "dt_pagamento"]
    assert reader.financeiro_reconcile_page.call_args_list[1].kwargs["cursor"] == (
        "2026-09-02", 123)
    assert not any("DELETE FROM" in str(call) for call in conn.execute.call_args_list)


@pytest.mark.parametrize("failure", [False, True])
def test_financial_watermark_commits_only_after_success(failure):
    conn, reader = MagicMock(), MagicMock()
    conn.closed = False
    conn.execute.return_value.fetchone.return_value = (True,)

    @contextmanager
    def pg(_):
        yield conn

    @contextmanager
    def source(*_):
        yield reader

    settings = MagicMock(spec=Settings)
    settings.batch_size = 100
    settings.reconciliation_days = 30

    def perform(*args, **kwargs):
        if failure:
            raise ValueError("private payload")
        return 123

    with patch.object(ativo_financeiro.postgres, "connect", pg), \
         patch.object(ativo_financeiro.mysql, "connect", source), \
         patch.object(financeiro.FinanceiroContract, "validate_schema"), \
         patch.object(ativo_financeiro, "load", side_effect=perform):
        if failure:
            with pytest.raises(ValueError):
                ativo_financeiro.run(settings, "FULL")
        else:
            assert isinstance(ativo_financeiro.run(settings, "FULL"), UUID)
    queries = [str(call.args[0]) for call in conn.execute.call_args_list]
    assert any("INSERT INTO raw._etl_watermark" in query for query in queries) == (not failure)
    assert any("status='FAILED'" in query for query in queries) == failure
    assert conn.rollback.call_count == int(failure)


def test_financial_cli_dispatch_and_transaction_reconcile_not_default():
    with patch("src.main.Settings.load"), patch("src.pipeline.ativo_financeiro.run") as run:
        assert main(["full", "--source", "ativo", "--entity", "pedido_pagamento"]) == 0
        assert main(["incremental", "--source", "ativo", "--entity", "transacao"]) == 0
        assert main(["reconcile", "--source", "ativo", "--entity", "transacao"]) == 0
    assert [call.kwargs["entity"] for call in run.call_args_list] == [
        "pedido_pagamento", "transacao", "transacao"]

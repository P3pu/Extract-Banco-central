from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.config.settings import Settings
from src.main import main
from src.pipeline import ativo_complementos
from src.sources.ativo import complementos


@pytest.mark.parametrize("contract", [complementos.pedido_produto, complementos.pedido_endereco])
def test_contract_schema_and_pk_pagination(contract):
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in contract.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": contract.PK, "SEQ_IN_INDEX": 1}]
    if contract.RECONCILE_BY_ORDER:
        indexes.append({"INDEX_NAME": "id_pedido", "COLUMN_NAME": "id_pedido", "SEQ_IN_INDEX": 1})
    contract.validate_schema(columns, indexes)
    query, params = contract.page_query(100, 500, cursor=300)
    assert params == (500, 300, 100)
    assert f"t.`{contract.PK}` > %s" in query and "ORDER BY" in query
    assert "OFFSET" not in query
    columns[0]["COLUMN_TYPE"] = "bigint(20)"
    with pytest.raises(ValueError, match=contract.PK):
        contract.validate_schema(columns, indexes)
    if contract.RECONCILE_BY_ORDER:
        columns[0]["COLUMN_TYPE"] = contract.FIELDS[contract.PK][0]
        with pytest.raises(ValueError, match="Índice id_pedido"):
            contract.validate_schema(columns, indexes[:1])


def test_address_reconciliation_uses_recent_orders_and_pk_keyset():
    query, params = complementos.pedido_endereco.reconcile_page_query(
        "2026-09-01", 1000, 200, cursor=500)
    assert params == ("2026-09-01", 1000, 500, 200)
    assert "FORCE INDEX (dt_pedido)" in query
    assert "STRAIGHT_JOIN" in query and "FORCE INDEX (id_pedido)" in query
    assert "e.`id_pedido_endereco` > %s" in query
    assert "OFFSET" not in query and "GROUP BY" not in query
    with pytest.raises(ValueError, match="Reconciliação inválida"):
        complementos.pedido_produto.reconcile_page_query("2026-09-01", 1000, 200)


def test_product_snapshot_deletes_stale_only_after_complete_extract():
    conn, reader = MagicMock(), MagicMock()
    reader.snapshot_bounds.return_value = (2, 20)
    reader.snapshot_page.side_effect = [[(10, 1, 2, 3, 4)], [(20, 1, 2, 3, 4)], []]
    conn.execute.side_effect = [MagicMock(), MagicMock(rowcount=1),
                                MagicMock(fetchone=MagicMock(return_value=(2,)))]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(ativo_complementos.loader, "prepare"), \
         patch.object(ativo_complementos.loader, "upsert", return_value=1):
        newest = ativo_complementos.load(conn, reader, "SNAPSHOT", 1,
                                        uuid4(), 5, 30, progress, "pedido_produto")
    assert newest == 20
    assert progress == {"rows_extracted": 2, "rows_loaded": 2, "rows_removed": 1}
    assert "DELETE FROM" in str(conn.execute.call_args_list[-2])
    assert reader.snapshot_page.call_args_list[1].kwargs["cursor"] == 10


def test_incomplete_snapshot_never_deletes_rows():
    conn, reader = MagicMock(), MagicMock()
    reader.snapshot_bounds.return_value = (2, 10)
    reader.snapshot_page.side_effect = [[(10, 1, 2, 3, 4)], []]
    with patch.object(ativo_complementos.loader, "prepare"), \
         patch.object(ativo_complementos.loader, "upsert", return_value=1):
        with pytest.raises(ValueError, match="Contagem de origem"):
            ativo_complementos.load(conn, reader, "SNAPSHOT", 1, uuid4(), 5, 30,
                                    {"rows_extracted": 0, "rows_loaded": 0}, "pedido_produto")
    assert not any("DELETE FROM" in str(call) for call in conn.execute.call_args_list)


def test_address_reconciliation_does_not_advance_watermark():
    conn, reader = MagicMock(), MagicMock()
    reader.snapshot_bounds.return_value = (None, 100)
    reader.ativo_pedido_cutoff.return_value = "2026-09-01"
    reader.pedido_endereco_reconcile_page.side_effect = [[(25, *([None] * 9))], []]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(ativo_complementos.loader, "prepare"), \
         patch.object(ativo_complementos.loader, "upsert", return_value=1):
        newest = ativo_complementos.load(conn, reader, "RECONCILIATION", 10,
                                        uuid4(), 90, 30, progress, "pedido_endereco")
    assert newest == 90
    assert progress == {"rows_extracted": 1, "rows_loaded": 1}
    assert reader.pedido_endereco_reconcile_page.call_args_list[1].kwargs["cursor"] == 25


@pytest.mark.parametrize("failure", [False, True])
def test_numeric_watermark_commits_only_after_success(failure):
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
        return 42

    with patch.object(ativo_complementos.postgres, "connect", pg), \
         patch.object(ativo_complementos.mysql, "connect", source), \
         patch.object(complementos.ComplementoContract, "validate_schema"), \
         patch.object(ativo_complementos, "load", side_effect=perform):
        if failure:
            with pytest.raises(ValueError):
                ativo_complementos.run(settings, "SNAPSHOT")
        else:
            assert isinstance(ativo_complementos.run(settings, "SNAPSHOT"), UUID)
    watermark_calls = [call for call in conn.execute.call_args_list
                       if "INSERT INTO raw._etl_watermark" in str(call.args[0])]
    assert bool(watermark_calls) == (not failure)
    if not failure:
        assert watermark_calls[0].args[1][-1] == "42"
    assert conn.rollback.call_count == int(failure)


def test_complement_cli_routes_modes():
    with patch("src.main.Settings.load"), \
         patch("src.pipeline.ativo_complementos.run") as run:
        assert main(["full", "--source", "ativo", "--entity", "pedido_produto"]) == 0
        assert main(["incremental", "--source", "ativo", "--entity", "pedido_endereco"]) == 0
        assert main(["reconcile", "--source", "ativo", "--entity", "pedido_endereco"]) == 0
        assert main(["snapshot", "--source", "ativo", "--entity", "pedido_produto"]) == 0
    assert [call.kwargs["entity"] for call in run.call_args_list] == [
        "pedido_produto", "pedido_endereco", "pedido_endereco", "pedido_produto"]
    assert run.call_args_list[-1].args[1] == "SNAPSHOT"

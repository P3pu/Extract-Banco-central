from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.config.settings import Settings
from src.db.mysql import MySQLReader
from src.main import main
from src.pipeline import ativo_usuario
from src.sources.ativo import usuarios


@pytest.mark.parametrize("contract", [usuarios.usuario, usuarios.usuario_balcao])
def test_user_contract_and_pk_pages(contract):
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "DATA_TYPE": "enum" if spec[0] == "enum" else spec[0].split("(")[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in contract.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": "id_usuario"}]
    contract.validate_schema(columns, indexes)
    query, params = contract.page_query(100, 500, cursor=300)
    assert params == (500, 300, 100)
    assert "u.`id_usuario` > %s" in query and "ORDER BY u.`id_usuario` LIMIT %s" in query
    assert "OFFSET" not in query and "GROUP BY" not in query
    columns[0]["COLUMN_TYPE"] = "bigint(20)"
    with pytest.raises(ValueError, match="id_usuario"):
        contract.validate_schema(columns, indexes)


def test_user_zero_dates_text_and_literal_types():
    assert usuarios.usuario.FIELDS["dt_nascimento"][1] == "TEXT"
    assert usuarios.usuario.FIELDS["data_create"][1] == "TEXT"
    assert usuarios.usuario.FIELDS["id_pais"][1] == "VARCHAR(11)"
    assert usuarios.usuario.FIELDS["ds_categoria_balcao"][1] == "TEXT"
    assert usuarios.usuario_balcao.FIELDS["id_usuario"][1] == "BIGINT"
    assert usuarios.usuario_balcao.FIELDS["dt_cadastro"][1] == "TEXT"
    query, _ = usuarios.usuario.page_query(10, 500)
    assert "CAST(u.`data_create` AS CHAR)" in query
    assert "CAST(u.`dt_nascimento` AS CHAR)" in query


def test_user_ids_query_is_parameterized():
    query, params = usuarios.usuario.ids_query([3, 1, 2])
    assert "IN (%s, %s, %s)" in query
    assert params == (3, 1, 2)
    with pytest.raises(ValueError, match="IDs"):
        usuarios.usuario.ids_query([])


def test_only_nul_is_replaced_without_changing_other_text():
    original = [(1, "a\x00b\x00ç", "normal"), (2, "sem alteração", None)]
    cleaned, count = ativo_usuario.replace_nul(original)
    assert cleaned == [(1, "a\ufffdb\ufffdç", "normal"), original[1]]
    assert count == 2
    assert original[0][1] == "a\x00b\x00ç"


def test_recent_references_use_indexed_join_without_aggregation():
    connection = MagicMock()
    mysql_cursor = connection.cursor.return_value.__enter__.return_value
    mysql_cursor.fetchall.return_value = ((10, 3),)
    reader = MySQLReader(connection)
    assert reader.recent_user_refs_page("id_usuario", datetime(2026, 8, 29),
                                        500, 100, cursor=20) == ((10, 3),)
    query, params = mysql_cursor.execute.call_args.args
    assert "STRAIGHT_JOIN sa_pedido_evento pe FORCE INDEX (id_pedido)" in query
    assert "pe.id_pedido_evento > %s" in query
    assert "GROUP BY" not in query and "DISTINCT" not in query
    assert params == (datetime(2026, 8, 29), 500, 20, 100)
    with pytest.raises(ValueError):
        reader.recent_user_refs_page("unsafe", datetime(2026, 8, 29), 500, 100)


def test_user_reconciliation_deduplicates_refs_without_advancing_watermark():
    conn, reader = MagicMock(), MagicMock()
    reader.snapshot_bounds.return_value = (None, 500)
    reader.ativo_pedido_evento_bounds.return_value = (None, 900)
    reader.ativo_pedido_cutoff.return_value = datetime(2026, 8, 29)
    reader.recent_user_refs_page.side_effect = [((100, 5), (101, 5), (102, 6)), ()]
    reader.usuario_ids.return_value = [(5, *([None] * 20)), (6, *([None] * 20))]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(ativo_usuario.loader, "validate_target"), patch.object(ativo_usuario.loader, "prepare"), \
         patch.object(ativo_usuario.loader, "upsert", return_value=2) as upsert:
        newest = ativo_usuario.load(conn, reader, "RECONCILIATION", 100,
                                    uuid4(), 499, 30, progress, "usuario")
    assert newest == 499
    assert progress == {"rows_extracted": 2, "rows_loaded": 2, "nul_replacements": 0}
    assert reader.usuario_ids.call_args.args[1] == [5, 6]
    assert reader.recent_user_refs_page.call_args_list[1].kwargs["cursor"] == 102
    assert upsert.call_count == 1


def test_user_full_count_mismatch_aborts():
    conn, reader = MagicMock(), MagicMock()
    reader.snapshot_bounds.return_value = (2, 10)
    reader.snapshot_page.side_effect = [[(10, *([None] * 20))], []]
    with patch.object(ativo_usuario.loader, "prepare"), \
         patch.object(ativo_usuario.loader, "upsert", return_value=1):
        with pytest.raises(ValueError, match="Contagem"):
            ativo_usuario.load(conn, reader, "FULL", 100, uuid4(), None, 30,
                               {"rows_extracted": 0, "rows_loaded": 0}, "usuario")


@pytest.mark.parametrize("failure", [False, True])
def test_user_watermark_only_on_success(failure):
    conn, reader = MagicMock(), MagicMock()
    conn.closed = False
    conn.execute.return_value.fetchone.side_effect = [(True,), None]

    @contextmanager
    def pg(_):
        yield conn

    @contextmanager
    def source(*_):
        yield reader

    settings = MagicMock(spec=Settings)
    settings.batch_size, settings.reconciliation_days = 100, 30

    def perform(*args):
        if failure:
            raise ValueError("private payload")
        return 500

    with patch.object(ativo_usuario.postgres, "connect", pg), \
         patch.object(ativo_usuario.mysql, "connect", source), \
         patch.object(usuarios.UsuarioContract, "validate_schema"), \
         patch.object(ativo_usuario, "load", side_effect=perform):
        if failure:
            with pytest.raises(ValueError):
                ativo_usuario.run(settings, "FULL")
        else:
            assert isinstance(ativo_usuario.run(settings, "FULL"), UUID)
    queries = [str(call.args[0]) for call in conn.execute.call_args_list]
    assert any("INSERT INTO raw._etl_watermark" in query for query in queries) == (not failure)
    assert any("status='FAILED'" in query for query in queries) == failure
    assert conn.rollback.call_count == int(failure)


def test_cli_routes_user_entities():
    with patch("src.main.Settings.load"), patch("src.pipeline.ativo_usuario.run") as run:
        assert main(["full", "--source", "ativo", "--entity", "usuario"]) == 0
        assert main(["incremental", "--source", "ativo", "--entity", "usuario_balcao"]) == 0
        assert main(["reconcile", "--source", "ativo", "--entity", "usuario"]) == 0
    assert [call.kwargs["entity"] for call in run.call_args_list] == [
        "usuario", "usuario_balcao", "usuario"]

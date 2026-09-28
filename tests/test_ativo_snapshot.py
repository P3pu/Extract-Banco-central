from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.config.settings import Settings
from src.main import main
from src.pipeline import ativo_snapshot
from src.sources.ativo import evento, referenciais


def test_evento_contract_and_zero_dates_as_text():
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in evento.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": "id_evento"}]
    evento.validate_schema(columns, indexes)
    assert evento.FIELDS["dt_evento"][1] == "TEXT"
    assert evento.FIELDS["dt_modificacao"][1] == "TEXT"
    assert evento.FIELDS["id_campanha_salesforce"][1] == "VARCHAR(50)"
    columns[0]["COLUMN_TYPE"] = "bigint(20)"
    with pytest.raises(ValueError, match="id_evento"):
        evento.validate_schema(columns, indexes)


def test_evento_pages_by_primary_key_without_offset():
    query, params = evento.page_query(100, 500, cursor=300)
    assert params == (500, 300, 100)
    assert "id_evento > %s" in query and "ORDER BY e.id_evento LIMIT %s" in query
    assert "CAST(e.`dt_evento` AS CHAR)" in query
    assert "CAST(e.`dt_modificacao` AS CHAR)" in query
    assert "OFFSET" not in query


def test_snapshot_deletes_stale_rows_only_after_complete_extract():
    conn, reader = MagicMock(), MagicMock()
    reader.snapshot_bounds.return_value = (2, 200)
    reader.snapshot_page.side_effect = [[(100, *([None] * 7))],
                                        [(200, *([None] * 7))], []]
    conn.execute.side_effect = [MagicMock(), MagicMock(rowcount=1),
                                MagicMock(fetchone=MagicMock(return_value=(2,)))]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(ativo_snapshot.loader, "prepare"), \
         patch.object(ativo_snapshot.loader, "upsert", return_value=1) as upsert:
        removed = ativo_snapshot.load(conn, reader, 1, uuid4(), progress)
    assert removed == 1
    assert progress == {"rows_extracted": 2, "rows_loaded": 2}
    assert reader.snapshot_page.call_args_list[1].kwargs["cursor"] == 100
    assert upsert.call_args.kwargs["pk"] == "id_evento"
    assert "DELETE FROM" in str(conn.execute.call_args_list[-2])


def test_snapshot_count_mismatch_does_not_delete():
    conn, reader = MagicMock(), MagicMock()
    reader.snapshot_bounds.return_value = (2, 100)
    reader.snapshot_page.side_effect = [[(100, *([None] * 7))], []]
    with patch.object(ativo_snapshot.loader, "prepare"), \
         patch.object(ativo_snapshot.loader, "upsert", return_value=1):
        with pytest.raises(ValueError, match="Contagem de origem"):
            ativo_snapshot.load(conn, reader, 1, uuid4(),
                                {"rows_extracted": 0, "rows_loaded": 0})
    assert not any("DELETE FROM" in str(call) for call in conn.execute.call_args_list)


def test_snapshot_replaces_only_nul_and_counts_replacements():
    conn, reader = MagicMock(), MagicMock()
    reader.snapshot_bounds.return_value = (1, 1)
    row = [None] * len(referenciais.cidade.COLUMNS)
    row[0], row[3] = 1, "A\x00B"
    reader.snapshot_page.side_effect = [[tuple(row)], []]
    conn.execute.side_effect = [MagicMock(), MagicMock(rowcount=0),
                                MagicMock(fetchone=MagicMock(return_value=(1,)))]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(ativo_snapshot.loader, "prepare"), \
         patch.object(ativo_snapshot.loader, "upsert", return_value=1) as upsert:
        ativo_snapshot.load(conn, reader, 10, uuid4(), progress, entity="cidade")
    assert upsert.call_args.args[1][0][3] == "A\ufffdB"
    assert row[3] == "A\x00B"
    assert progress == {"rows_extracted": 1, "rows_loaded": 1, "nul_replacements": 1}


def test_snapshot_cli_routes_evento():
    with patch("src.main.Settings.load"), \
         patch("src.pipeline.ativo_snapshot.run") as run, \
         patch("src.pipeline.ativo_complementos.run") as product_run:
        assert main(["snapshot"]) == 0
        assert main(["snapshot", "--source", "ativo", "--entity", "evento", "--batch-size", "500"]) == 0
    count = len(ativo_snapshot.ENTITIES)
    assert [call.kwargs["entity"] for call in run.call_args_list[:count]] == list(ativo_snapshot.ENTITIES)
    assert run.call_count == count + 1
    assert run.call_args_list[count].args[1] == 500
    assert run.call_args_list[count].kwargs["entity"] == "evento"
    assert product_run.call_count == 1
    assert product_run.call_args.args[1] == "SNAPSHOT"


@pytest.mark.parametrize("contract", [referenciais.evento_modalidade,
                                      referenciais.modalidade_categoria,
                                      referenciais.pedido_status,
                                      referenciais.tamanho_camiseta,
                                      referenciais.formas_pagamento,
                                      referenciais.produto,
                                      referenciais.combo,
                                      referenciais.cidade,
                                      referenciais.estado,
                                      referenciais.pais])
def test_reference_contracts_validate_schema_and_keyset(contract):
    columns = [{"COLUMN_NAME": name, "COLUMN_TYPE": spec[0],
                "IS_NULLABLE": "YES" if spec[2] else "NO"}
               for name, spec in contract.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": contract.PK}]
    contract.validate_schema(columns, indexes)
    query, params = contract.page_query(100, 500, cursor=300)
    assert params == (500, 300, 100)
    assert f"t.`{contract.PK}` > %s" in query
    assert "OFFSET" not in query
    columns[0]["COLUMN_TYPE"] = "bigint(20)"
    with pytest.raises(ValueError, match=contract.PK):
        contract.validate_schema(columns, indexes)


def test_modalidade_zero_date_remains_text():
    contract = referenciais.evento_modalidade
    assert contract.FIELDS["data_update"][1] == "TEXT"
    query, _ = contract.page_query(10, 100)
    assert "CAST(t.`data_update` AS CHAR)" in query
    assert referenciais.modalidade_categoria.FIELDS["data_update"][1] == "TIMESTAMP"


def test_tamanho_all_source_columns_and_unsigned_ids():
    assert len(referenciais.tamanho_camiseta.COLUMNS) == 7
    assert referenciais.tamanho_camiseta.FIELDS["nr_peso"][1] == "NUMERIC(10,2)"
    assert referenciais.produto.FIELDS["id_produto"][1] == "BIGINT"
    assert referenciais.combo.FIELDS["id_combo"][1] == "BIGINT"


def test_geography_uses_physical_primary_keys_and_original_fields():
    assert referenciais.cidade.PK == "id"
    assert referenciais.estado.PK == "id"
    assert referenciais.pais.PK == "id_pais"
    assert len(referenciais.cidade.COLUMNS) == 17
    assert len(referenciais.estado.COLUMNS) == 7
    assert len(referenciais.pais.COLUMNS) == 9


@pytest.mark.parametrize("failure", [False, True])
def test_snapshot_watermark_commits_only_after_success(failure):
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

    def perform(*args, **kwargs):
        if failure:
            raise ValueError("private payload")
        return 0

    with patch.object(ativo_snapshot.postgres, "connect", pg), \
         patch.object(ativo_snapshot.mysql, "connect", source), \
         patch.object(evento, "validate_schema"), \
         patch.object(ativo_snapshot, "load", side_effect=perform):
        if failure:
            with pytest.raises(ValueError):
                ativo_snapshot.run(settings)
        else:
            assert isinstance(ativo_snapshot.run(settings), UUID)
    queries = [str(call.args[0]) for call in conn.execute.call_args_list]
    assert any("INSERT INTO raw._etl_watermark" in query for query in queries) == (not failure)
    assert any("status='FAILED'" in query for query in queries) == failure
    assert conn.rollback.call_count == int(failure)

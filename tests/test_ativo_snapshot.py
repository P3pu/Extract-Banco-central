from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.main import main
from src.pipeline import ativo_snapshot
from src.sources.ativo import evento


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
    reader.ativo_evento_bounds.return_value = (2, 200)
    reader.ativo_evento_page.side_effect = [[(100, *([None] * 7))],
                                             [(200, *([None] * 7))], []]
    conn.execute.side_effect = [MagicMock(), MagicMock(rowcount=1),
                                MagicMock(fetchone=MagicMock(return_value=(2,)))]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(ativo_snapshot.loader, "prepare"), \
         patch.object(ativo_snapshot.loader, "upsert", return_value=1) as upsert:
        removed = ativo_snapshot.load(conn, reader, 1, uuid4(), progress)
    assert removed == 1
    assert progress == {"rows_extracted": 2, "rows_loaded": 2}
    assert reader.ativo_evento_page.call_args_list[1].kwargs["cursor"] == 100
    assert upsert.call_args.kwargs["pk"] == "id_evento"
    assert "DELETE FROM" in str(conn.execute.call_args_list[-2])


def test_snapshot_count_mismatch_does_not_delete():
    conn, reader = MagicMock(), MagicMock()
    reader.ativo_evento_bounds.return_value = (2, 100)
    reader.ativo_evento_page.side_effect = [[(100, *([None] * 7))], []]
    with patch.object(ativo_snapshot.loader, "prepare"), \
         patch.object(ativo_snapshot.loader, "upsert", return_value=1):
        with pytest.raises(ValueError, match="Contagem de origem"):
            ativo_snapshot.load(conn, reader, 1, uuid4(),
                                {"rows_extracted": 0, "rows_loaded": 0})
    assert not any("DELETE FROM" in str(call) for call in conn.execute.call_args_list)


def test_snapshot_cli_routes_evento():
    with patch("src.main.Settings.load"), patch("src.pipeline.ativo_snapshot.run") as run:
        assert main(["snapshot"]) == 0
        assert main(["snapshot", "--source", "ativo", "--entity", "evento", "--batch-size", "500"]) == 0
    assert run.call_count == 2
    assert run.call_args_list[1].args[1] == 500
    assert run.call_args_list[1].kwargs["entity"] == "evento"

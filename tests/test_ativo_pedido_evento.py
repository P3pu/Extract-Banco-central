from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.main import main
from src.pipeline import ativo_pedido as pipeline
from src.sources.ativo import pedido_evento


def test_full_and_incremental_use_pk_without_filters():
    for mode in ("FULL", "INCREMENTAL"):
        query, params = pedido_evento.page_query(mode, 100, 500, cursor=300)
        assert params == (500, 300, 100)
        assert "FORCE INDEX (PRIMARY)" in query
        assert "id_pedido_evento > %s" in query
        assert "GROUP BY" not in query and "DISTINCT" not in query and "OFFSET" not in query


def test_reconciliation_joins_recent_orders_without_aggregation():
    cutoff = datetime(2026, 8, 29)
    query, params = pedido_evento.page_query("RECONCILIATION", 100, 500,
                                              cursor=300, cutoff=cutoff)
    assert params == (cutoff, 500, 300, 100)
    assert "sa_pedido p FORCE INDEX (dt_pedido) STRAIGHT_JOIN sa_pedido_evento pe" in query
    assert "ON pe.id_pedido = p.id_pedido" in query
    assert "pe.id_pedido_evento > %s" in query
    assert "GROUP BY" not in query and "DISTINCT" not in query


def test_reconciliation_requires_window():
    with pytest.raises(ValueError, match="Janela"):
        pedido_evento.page_query("RECONCILIATION", 10, 500)


def test_source_schema_preserves_textual_prices():
    columns = [{"COLUMN_NAME": n, "COLUMN_TYPE": t[0], "IS_NULLABLE": "YES" if t[2] else "NO"}
               for n, t in pedido_evento.FIELDS.items()]
    indexes = [{"INDEX_NAME": "PRIMARY", "COLUMN_NAME": pedido_evento.PK, "SEQ_IN_INDEX": 1},
               {"INDEX_NAME": "id_pedido", "COLUMN_NAME": "id_pedido", "SEQ_IN_INDEX": 1}]
    pedido_evento.validate_schema(columns, indexes)
    assert pedido_evento.FIELDS["nr_desconto_individual"][1] == "VARCHAR(150)"
    assert pedido_evento.FIELDS["nr_preco_nm_camiseta"][1] == "VARCHAR(150)"
    assert pedido_evento.FIELDS["fl_amigo"][1] == "VARCHAR(1)"
    columns[-1]["COLUMN_TYPE"] = "datetime"
    with pytest.raises(ValueError, match="dt_cadastro"):
        pedido_evento.validate_schema(columns, indexes)


def test_event_reconciliation_does_not_advance_pk_watermark():
    conn, reader = MagicMock(), MagicMock()
    reader.ativo_pedido_evento_bounds.return_value = (None, 500)
    reader.ativo_pedido_cutoff.return_value = datetime(2026, 8, 29)
    row = [None] * len(pedido_evento.COLUMNS)
    row[0], row[1] = 400, 10
    reader.ativo_pedido_evento_page.side_effect = [(tuple(row),), ()]
    with patch.object(pipeline.loader, "prepare"), patch.object(pipeline.loader, "upsert", return_value=1) as upsert:
        result = pipeline.load(conn, reader, "RECONCILIATION", 10, uuid4(), 350, 30,
                               {"rows_extracted": 0, "rows_loaded": 0}, entity="pedido_evento")
    assert result == 350
    assert reader.ativo_pedido_evento_page.call_args_list[1].kwargs["cursor"] == 400
    assert upsert.call_args.kwargs["source"] == "ativo"
    assert upsert.call_args.kwargs["pk"] == "id_pedido_evento"


def test_cli_routes_event_entity_only():
    with patch("src.main.Settings.load"), patch("src.pipeline.ativo_pedido.run") as run:
        assert main(["incremental", "--source", "ativo", "--entity", "pedido_evento"]) == 0
        assert main(["reconcile", "--source", "ativo", "--entity", "pedido_evento", "--days", "7"]) == 0
    assert run.call_count == 2
    assert all(c.kwargs["entity"] == "pedido_evento" for c in run.call_args_list)
    assert run.call_args_list[1].args[1] == "RECONCILIATION"

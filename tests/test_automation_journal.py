from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.automation.change_journal import ChangeJournal
from src.pipeline import ativo_pedido, sales_order
from src.sources.ativo import pedido_evento
from src.sources.magento import sales_order_item


def _row(columns, **values):
    return tuple(values.get(name) for name in columns)


def test_journal_records_only_ids_and_survives_reopen(tmp_path):
    path = tmp_path / "pending.sqlite"
    journal = ChangeJournal(path)
    item = _row(sales_order_item.COLUMNS, item_id=41, parent_item_id=40, order_id=9)
    journal.record_rows("magento", "sales_order_item", UUID(int=1), [item], sales_order_item.COLUMNS)
    event = _row(pedido_evento.COLUMNS, id_pedido_evento=91, id_pedido=None)
    journal.record_rows("ativo", "pedido_evento", UUID(int=2), [event], pedido_evento.COLUMNS)
    journal.close()
    journal = ChangeJournal(path)
    assert journal.snapshot() == [
        ("ativo", "inscription", 91, None),
        ("magento", "inscription", 40, 9),
    ]
    journal.clear()
    assert journal.snapshot() == []
    journal.close()


@pytest.mark.parametrize("pipeline,entity,contract,reader_method,bounds", [
    (sales_order, "sales_order_item", sales_order_item,
     "sales_order_item_page", (None, 42, None)),
    (ativo_pedido, "pedido_evento", pedido_evento,
     "ativo_pedido_evento_page", (None, 92)),
])
def test_callback_failure_prevents_pipeline_commit(pipeline, entity, contract,
                                                   reader_method, bounds):
    connection, reader = MagicMock(), MagicMock()
    getattr(reader, f"{entity}_bounds" if pipeline is sales_order else
            f"ativo_{entity}_bounds").return_value = bounds
    row = _row(contract.COLUMNS, **({"item_id": 41, "order_id": 9, "updated_at": None}
                                   if pipeline is sales_order else
                                   {"id_pedido_evento": 91, "id_pedido": 8}))
    getattr(reader, reader_method).side_effect = [(row,), ()]
    callback = MagicMock(side_effect=RuntimeError("journal unavailable"))
    with patch.object(pipeline.loader, "validate_target"), \
         patch.object(pipeline.loader, "prepare"), \
         patch.object(pipeline.loader, "upsert", return_value=1):
        with pytest.raises(RuntimeError, match="journal unavailable"):
            if pipeline is sales_order:
                pipeline.load(connection, reader, "INCREMENTAL", 10, UUID(int=1),
                              None, {"rows_extracted": 0, "rows_loaded": 0},
                              entity=entity, on_rows=callback)
            else:
                pipeline.load(connection, reader, "INCREMENTAL", 10, UUID(int=1),
                              0, 30, {"rows_extracted": 0, "rows_loaded": 0},
                              entity=entity, on_rows=callback)
    callback.assert_called_once()

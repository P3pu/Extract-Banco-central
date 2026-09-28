import os
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.ativo import financeiro

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


@pytest.mark.parametrize("contract", [financeiro.pedido_pagamento, financeiro.transacao])
def test_financial_source_schema_and_pages(contract):
    settings = Settings.load()
    with mysql.connect(settings, "ativo") as reader:
        db = settings.database("ativo").database
        contract.validate_schema(reader.columns(db, contract.TABLE),
                                 reader.indexes(db, contract.TABLE))
        _, upper = reader.snapshot_bounds(contract, count_total=False)
        first = reader.snapshot_page(contract, batch_size=5, upper_id=upper)
        second = reader.snapshot_page(contract, batch_size=5, upper_id=upper,
                                      cursor=first[-1][0])
        assert len(first) == len(second) == 5
        assert first[-1][0] < second[0][0]


def test_payment_reconcile_indexed_page():
    with mysql.connect(Settings.load(), "ativo") as reader:
        _, upper = reader.snapshot_bounds(financeiro.pedido_pagamento, count_total=False)
        cutoff = reader.ativo_pedido_cutoff(30)
        for column in financeiro.pedido_pagamento.RECON_DATES:
            rows = reader.financeiro_reconcile_page(
                financeiro.pedido_pagamento, cutoff=cutoff, upper_id=upper,
                batch_size=5, date_column=column)
            assert len(rows) <= 5
            if rows:
                date_index = financeiro.pedido_pagamento.COLUMNS.index(column)
                cursor = (rows[-1][date_index], rows[-1][0])
                following = reader.financeiro_reconcile_page(
                    financeiro.pedido_pagamento, cutoff=cutoff, upper_id=upper,
                    batch_size=5, cursor=cursor, date_column=column)
                assert not following or following[0][0] != rows[-1][0]


@pytest.mark.parametrize("contract,ddl,values", [
    (financeiro.pedido_pagamento, "019_create_ativo_pedido_pagamento_raw.sql",
     {"id_pedido_pagamento": 1, "id_pedido": 2, "id_formas_pagamento": 3,
      "fl_status": "PENDENTE", "dt_registro": "2026-01-01 00:00:00",
      "dt_pagamento": "0000-00-00 00:00:00"}),
    (financeiro.transacao, "020_create_ativo_transacao_raw.sql",
     {"id_transacao": 1, "id_pedido_pagamento": 2,
      "dt_cadastro": "2026-01-01 00:00:00"}),
])
def test_financial_temp_copy(contract, ddl, values):
    with postgres.connect(Settings.load()) as conn:
        ddl_text = (ROOT / "sql/postgres" / ddl).read_text(encoding="utf-8")
        conn.execute(ddl_text.replace(f"CREATE TABLE IF NOT EXISTS raw.ativo_{contract.TABLE[3:]}",
                                      "CREATE TEMP TABLE integration_financial"))
        target = ("pg_temp", "integration_financial")
        loader.prepare(conn, target)
        row = tuple(values.get(name) for name in contract.COLUMNS)
        assert loader.upsert(conn, [row], uuid4(), target, contract.COLUMNS,
                             contract.PK, "ativo") == 1
        assert conn.execute("SELECT COUNT(*) FROM pg_temp.integration_financial").fetchone()[0] == 1
        if contract is financeiro.pedido_pagamento:
            assert conn.execute("SELECT dt_pagamento FROM pg_temp.integration_financial").fetchone()[0] == (
                "0000-00-00 00:00:00")

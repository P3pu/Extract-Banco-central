import os
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.ativo import complementos

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


@pytest.mark.parametrize("contract", [complementos.pedido_produto,
                                      complementos.pedido_endereco])
def test_source_schema_and_pk_pages(contract):
    s = Settings.load()
    with mysql.connect(s, "ativo") as reader:
        db = s.database("ativo").database
        contract.validate_schema(reader.columns(db, contract.TABLE),
                                 reader.indexes(db, contract.TABLE))
        _, upper = reader.snapshot_bounds(contract, count_total=False)
        first = reader.snapshot_page(contract, batch_size=5, upper_id=upper)
        second = reader.snapshot_page(contract, batch_size=5, upper_id=upper,
                                      cursor=first[-1][0])
        assert len(first) == len(second) == 5
        assert first[-1][0] < second[0][0]


def test_address_recent_order_page():
    with mysql.connect(Settings.load(), "ativo") as reader:
        _, upper = reader.snapshot_bounds(complementos.pedido_endereco, count_total=False)
        cutoff = reader.ativo_pedido_cutoff(30)
        rows = reader.pedido_endereco_reconcile_page(
            complementos.pedido_endereco, cutoff=cutoff, upper_id=upper, batch_size=5)
        assert len(rows) <= 5
        if rows:
            following = reader.pedido_endereco_reconcile_page(
                complementos.pedido_endereco, cutoff=cutoff, upper_id=upper,
                batch_size=5, cursor=rows[-1][0])
            assert not following or rows[-1][0] < following[0][0]


@pytest.mark.parametrize("contract,ddl,values", [
    (complementos.pedido_produto, "021_create_ativo_pedido_produto_raw.sql",
     {"id_pedido_produto": 1, "id_pedido": 2, "id_produto": 3,
      "nr_preco": "12.34", "nr_quantidade": 2}),
    (complementos.pedido_endereco, "022_create_ativo_pedido_endereco_raw.sql",
     {"id_pedido_endereco": 1, "id_pedido": 2, "id_cidade": 3,
      "ds_endereco": "teste", "ds_num": "", "ds_complemento": "",
      "ds_bairro": "teste", "nr_cep": "12345", "dt_cadastro": "2026-01-01 00:00:00"}),
])
def test_temp_copy_preserves_fields(contract, ddl, values):
    with postgres.connect(Settings.load()) as conn:
        ddl_text = (ROOT / "sql/postgres" / ddl).read_text(encoding="utf-8")
        conn.execute(ddl_text.replace(f"CREATE TABLE IF NOT EXISTS raw.ativo_{contract.TABLE[3:]}",
                                      "CREATE TEMP TABLE integration_complement"))
        target = ("pg_temp", "integration_complement")
        loader.prepare(conn, target)
        row = tuple(values.get(name) for name in contract.COLUMNS)
        assert loader.upsert(conn, [row], uuid4(), target, contract.COLUMNS,
                             contract.PK, "ativo") == 1
        assert conn.execute("SELECT COUNT(*) FROM pg_temp.integration_complement").fetchone()[0] == 1
        if contract is complementos.pedido_endereco:
            assert conn.execute("SELECT ds_num,ds_complemento FROM pg_temp.integration_complement").fetchone() == ("", "")

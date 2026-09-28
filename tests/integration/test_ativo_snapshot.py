import os

import pytest

from src.config.settings import Settings
from src.db import mysql, postgres
from src.sources.ativo import evento, referenciais

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="RUN_INTEGRATION=1 necessário")


def test_evento_source_schema_and_zero_dates():
    settings = Settings.load()
    with mysql.connect(settings, "ativo") as reader:
        db = settings.database("ativo").database
        evento.validate_schema(reader.columns(db, "sa_evento"), reader.indexes(db, "sa_evento"))
        count, upper = reader.snapshot_bounds(evento)
        assert count > 0 and upper >= count
        rows = reader.snapshot_page(evento, batch_size=5, upper_id=upper)
        assert len(rows) == 5
        assert [row[0] for row in rows] == sorted(row[0] for row in rows)


def test_evento_temp_table_preserves_empty_dates_and_rollback():
    from datetime import datetime
    from uuid import uuid4

    from src.config.settings import ROOT
    from src.loaders import postgres_loader as loader

    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/006_create_ativo_evento_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.ativo_evento",
                                 "CREATE TEMP TABLE integration_evento"))
        target = ("pg_temp", "integration_evento")
        loader.prepare(conn, target)
        values = {"id_evento": 1, "ds_evento": "teste", "dt_evento": "0000-00-00 00:00:00",
                  "dt_modificacao": "0000-00-00 00:00:00", "data_update": datetime(2026, 1, 1)}
        row = tuple(values.get(name) for name in evento.COLUMNS)
        batch_id = uuid4()
        loader.upsert(conn, [row], batch_id, target, evento.COLUMNS, evento.PK, "ativo")
        assert conn.execute("SELECT dt_evento,dt_modificacao FROM pg_temp.integration_evento").fetchone() == (
            "0000-00-00 00:00:00", "0000-00-00 00:00:00")
        with pytest.raises(RuntimeError):
            with conn.transaction():
                conn.execute("DELETE FROM pg_temp.integration_evento")
                raise RuntimeError("rollback simulado")
        assert conn.execute("SELECT COUNT(*) FROM pg_temp.integration_evento").fetchone()[0] == 1


@pytest.mark.parametrize("contract", [referenciais.evento_modalidade,
                                      referenciais.modalidade_categoria,
                                      referenciais.pedido_status])
def test_reference_source_schema_and_pagination(contract):
    settings = Settings.load()
    with mysql.connect(settings, "ativo") as reader:
        db = settings.database("ativo").database
        contract.validate_schema(reader.columns(db, contract.TABLE),
                                 reader.indexes(db, contract.TABLE))
        count, upper = reader.snapshot_bounds(contract)
        assert count > 0 and upper >= count
        first = reader.snapshot_page(contract, batch_size=5, upper_id=upper)
        second = reader.snapshot_page(contract, batch_size=5, upper_id=upper,
                                      cursor=first[-1][0])
        assert len(first) == 5
        assert first[-1][0] < second[0][0]

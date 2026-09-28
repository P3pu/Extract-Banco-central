"""Opt-in: somente metadados da origem e tabelas TEMP no destino."""
import os
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.ativo import pedido

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="RUN_INTEGRATION=1 necessário")


def test_source_contract():
    settings = Settings.load()
    with mysql.connect(settings, "ativo") as reader:
        db = settings.database("ativo").database
        pedido.validate_schema(reader.columns(db, "sa_pedido"), reader.indexes(db, "sa_pedido"))


def test_zero_dates_copy_upsert_and_rollback():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/004_create_ativo_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.ativo_pedido", "CREATE TEMP TABLE integration_pedido"))
        target = ("pg_temp", "integration_pedido")
        loader.prepare(conn, target)
        values = dict(id_pedido=5, id_pedido_status=1, dt_pedido="0000-00-00 00:00:00",
                      dt_alteracao="0000-00-00 00:00:00", nr_desconto=Decimal("0.00"))
        row = tuple(values.get(n) for n in pedido.COLUMNS)
        batch_id = uuid4()
        assert loader.upsert(conn, [row], batch_id, target, columns=pedido.COLUMNS,
                             pk=pedido.PK, source="ativo") == 1
        with conn.transaction():
            values["dt_pedido"] = datetime(2026, 9, 28, 11)
            values["nr_desconto"] = Decimal("5.50")
            loader.upsert(conn, [tuple(values.get(n) for n in pedido.COLUMNS)], batch_id,
                          target, columns=pedido.COLUMNS, pk=pedido.PK, source="ativo")
        result = conn.execute("SELECT count(*), max(dt_alteracao), max(nr_desconto), max(_source) "
                              "FROM pg_temp.integration_pedido").fetchone()
        assert result == (1, "0000-00-00 00:00:00", Decimal("5.50"), "ativo")
        with pytest.raises(RuntimeError):
            with conn.transaction():
                loader.upsert(conn, [row], uuid4(), target, columns=pedido.COLUMNS,
                              pk=pedido.PK, source="ativo")
                raise RuntimeError("rollback simulado")
        assert conn.execute("SELECT nr_desconto FROM pg_temp.integration_pedido").fetchone()[0] == Decimal("5.50")

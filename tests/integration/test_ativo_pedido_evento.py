import os
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.ativo import pedido_evento

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="RUN_INTEGRATION=1 necessário")


def test_source_contract_and_join_plan():
    settings = Settings.load()
    with mysql.connect(settings, "ativo") as reader:
        db = settings.database("ativo").database
        pedido_evento.validate_schema(reader.columns(db, "sa_pedido_evento"),
                                      reader.indexes(db, "sa_pedido_evento"))
        query, params = pedido_evento.page_query("RECONCILIATION", 100, 19570267,
                                                 cutoff=datetime(2026, 8, 29))
        with reader._connection.cursor() as cursor:
            cursor.execute("EXPLAIN " + query, params)
            plan = cursor.fetchall()
        assert len(plan) == 2
        assert plan[0][2] == "p" and plan[1][2] == "pe"


def test_copy_upsert_text_and_rollback():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/005_create_ativo_pedido_evento_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.ativo_pedido_evento", "CREATE TEMP TABLE integration_evento"))
        target = ("pg_temp", "integration_evento")
        loader.prepare(conn, target)
        values = dict(id_pedido_evento=308, id_pedido=5, id_evento=1, id_usuario=1,
                      nr_preco=Decimal("59.00"), nr_taxa=Decimal("1.2345"),
                      nr_desconto_individual="texto literal 10,5%",
                      nr_preco_nm_camiseta="incluído", fl_amigo="",
                      dt_cadastro=datetime(2026, 1, 1))
        row = tuple(values.get(n) for n in pedido_evento.COLUMNS)
        batch_id = uuid4()
        for _ in range(2):
            assert loader.upsert(conn, [row], batch_id, target, columns=pedido_evento.COLUMNS,
                                 pk=pedido_evento.PK, source="ativo") == 1
        selected = conn.execute("SELECT count(*),max(nr_desconto_individual),max(nr_taxa),"
                                "max(fl_amigo),max(_source) FROM pg_temp.integration_evento").fetchone()
        assert selected == (1, "texto literal 10,5%", Decimal("1.2345"), "", "ativo")
        with pytest.raises(RuntimeError):
            with conn.transaction():
                loader.upsert(conn, [row], uuid4(), target, columns=pedido_evento.COLUMNS,
                              pk=pedido_evento.PK, source="ativo")
                raise RuntimeError("rollback simulado")
        assert conn.execute("SELECT _batch_id FROM pg_temp.integration_evento").fetchone()[0] == batch_id

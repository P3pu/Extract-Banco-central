import os
from datetime import datetime
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.ativo import usuarios

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="RUN_INTEGRATION=1 necessário")


@pytest.mark.parametrize("contract", [usuarios.usuario, usuarios.usuario_balcao])
def test_source_schema_and_keyset(contract):
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
        assert len(first) == 5 and first[-1][0] < second[0][0]


def test_recent_user_join_plan():
    settings = Settings.load()
    with mysql.connect(settings, "ativo") as reader:
        with reader._connection.cursor() as cursor:
            query = ("EXPLAIN SELECT pe.id_pedido_evento,pe.id_usuario FROM sa_pedido p "
                     "FORCE INDEX (dt_pedido) STRAIGHT_JOIN sa_pedido_evento pe "
                     "FORCE INDEX (id_pedido) ON pe.id_pedido=p.id_pedido "
                     "WHERE p.dt_pedido >= %s ORDER BY pe.id_pedido_evento LIMIT 10")
            cursor.execute(query, (datetime(2026, 8, 29),))
            plan = cursor.fetchall()
        assert [part[2] for part in plan] == ["p", "pe"]


@pytest.mark.parametrize("contract,ddl,values", [
    (usuarios.usuario, "010_create_ativo_usuario_raw.sql",
     {"id_usuario": 1, "ds_nome": "teste", "fl_sexo": "",
      "dt_nascimento": "0000-00-00", "data_create": "0000-00-00 00:00:00",
      "data_update": datetime(2026, 1, 1)}),
    (usuarios.usuario_balcao, "011_create_ativo_usuario_balcao_raw.sql",
     {"id_usuario": 1, "ds_nome": "teste", "fl_sexo": "", "nr_documento": "x",
      "dt_nascimento": "0000-00-00 00:00:00", "ds_email": "x@example.invalid",
      "ds_telefone": "", "ds_celular": "", "pelotao": "",
      "dt_cadastro": "0000-00-00 00:00:00"}),
])
def test_temp_copy_preserves_zero_dates_and_rollback(contract, ddl, values):
    with postgres.connect(Settings.load()) as conn:
        sql_text = (ROOT / "sql/postgres" / ddl).read_text(encoding="utf-8")
        conn.execute(sql_text.replace(f"CREATE TABLE IF NOT EXISTS raw.ativo_{contract.TABLE[3:]}",
                                      "CREATE TEMP TABLE integration_usuario"))
        target = ("pg_temp", "integration_usuario")
        loader.prepare(conn, target)
        row = tuple(values.get(name) for name in contract.COLUMNS)
        batch_id = uuid4()
        assert loader.upsert(conn, [row], batch_id, target, contract.COLUMNS,
                             contract.PK, "ativo") == 1
        fields = ", ".join(contract.TEXT_DATES)
        assert conn.execute(f"SELECT {fields} FROM pg_temp.integration_usuario").fetchone() == tuple(
            values[name] for name in contract.TEXT_DATES)
        with pytest.raises(RuntimeError):
            with conn.transaction():
                conn.execute("DELETE FROM pg_temp.integration_usuario")
                raise RuntimeError("rollback simulado")
        assert conn.execute("SELECT COUNT(*) FROM pg_temp.integration_usuario").fetchone()[0] == 1

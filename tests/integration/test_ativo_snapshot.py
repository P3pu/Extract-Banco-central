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
                                      referenciais.pedido_status,
                                      referenciais.tamanho_camiseta,
                                      referenciais.formas_pagamento,
                                      referenciais.produto,
                                      referenciais.combo,
                                      referenciais.cidade,
                                      referenciais.estado,
                                      referenciais.pais])
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


@pytest.mark.parametrize("contract,ddl,values", [
    (referenciais.tamanho_camiseta, "012_create_ativo_tamanho_camiseta_raw.sql",
     {"id_tamanho_camiseta": 2, "ds_tamanho": "teste", "id_situacao_cadastro": 1,
      "disponivel_atleta": 0}),
    (referenciais.formas_pagamento, "013_create_ativo_formas_pagamento_raw.sql",
     {"id_formas_pagamento": 1, "ds_descricao": "teste"}),
    (referenciais.produto, "014_create_ativo_produto_raw.sql",
     {"id_produto": 1, "ds_titulo": "teste"}),
    (referenciais.combo, "015_create_ativo_combo_raw.sql",
     {"id_combo": 5, "ds_titulo": "teste"}),
    (referenciais.cidade, "016_create_ativo_cidade_raw.sql",
     {"id": 1, "id_pais": 1, "id_estado": 1, "id_cidade": 1,
      "ds_cidade": "teste", "ds_cidade_en": "test", "ds_cidade_es": "prueba",
      "nr_cep": "12345", "latitude": "0", "longitude": "0", "nr_ibge": 0,
      "id_situacao_cadastro": 1, "id_pais_origem": 1, "atualizado": 0,
      "status": "ativo", "ativo": 1}),
    (referenciais.estado, "017_create_ativo_estado_raw.sql",
     {"id": 1, "id_pais": 1, "id_estado": 1, "ds_estado": "teste",
      "ds_estado_en": "test", "ds_sigla": "TS"}),
    (referenciais.pais, "018_create_ativo_pais_raw.sql",
     {"id_pais": 1, "ds_pais": "teste", "ds_pais_en": "test",
      "ds_pais_es": "prueba"}),
])
def test_reference_temporary_copy(contract, ddl, values):
    from uuid import uuid4

    from src.config.settings import ROOT
    from src.loaders import postgres_loader as loader

    with postgres.connect(Settings.load()) as conn:
        ddl_text = (ROOT / "sql/postgres" / ddl).read_text(encoding="utf-8")
        conn.execute(ddl_text.replace(f"CREATE TABLE IF NOT EXISTS raw.ativo_{contract.TABLE[3:]}",
                                      "CREATE TEMP TABLE integration_ref"))
        target = ("pg_temp", "integration_ref")
        loader.prepare(conn, target)
        row = tuple(values.get(name) for name in contract.COLUMNS)
        assert loader.upsert(conn, [row], uuid4(), target, contract.COLUMNS,
                             contract.PK, "ativo") == 1
        assert conn.execute("SELECT COUNT(*) FROM pg_temp.integration_ref").fetchone()[0] == 1

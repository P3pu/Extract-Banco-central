import os
from uuid import uuid4

import pytest

from src.config.settings import ROOT, Settings
from src.db import mysql, postgres
from src.loaders import postgres_loader as loader
from src.sources.ativo import cupom

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                                reason="RUN_INTEGRATION=1 necessário")


def test_coupon_source_schema_and_indexed_pages():
    s = Settings.load()
    with mysql.connect(s, "ativo") as reader:
        db = s.database("ativo").database
        cupom.validate_schema(reader.columns(db, cupom.TABLE),
                              reader.indexes(db, cupom.TABLE))
        _, upper = reader.snapshot_bounds(cupom, count_total=False)
        first = reader.snapshot_page(cupom, batch_size=5, upper_id=upper)
        second = reader.snapshot_page(cupom, batch_size=5, upper_id=upper,
                                      cursor=first[-1][0])
        by_id = reader.cupom_ids(cupom, [row[0] for row in first], upper)
        assert len(first) == len(second) == len(by_id) == 5
        assert first[-1][0] < second[0][0]
        assert by_id == first


def test_coupon_temp_copy_preserves_empty_flag_and_zero_dates():
    with postgres.connect(Settings.load()) as conn:
        ddl = (ROOT / "sql/postgres/023_create_ativo_cupom_desconto_item_raw.sql").read_text(encoding="utf-8")
        conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS raw.ativo_cupom_desconto_item",
                                 "CREATE TEMP TABLE integration_cupom"))
        target = ("pg_temp", "integration_cupom")
        loader.prepare(conn, target)
        values = {"id_cupom_desconto_item": 1, "nr_cupom": "teste",
                  "fl_usado": "", "dt_sistema": "0000-00-00 00:00:00",
                  "dt_uso": "0000-00-00 00:00:00", "id_cupom_desconto": 2}
        row = tuple(values.get(name) for name in cupom.COLUMNS)
        assert loader.upsert(conn, [row], uuid4(), target, cupom.COLUMNS,
                             cupom.PK, "ativo") == 1
        assert conn.execute("SELECT fl_usado,dt_sistema,dt_uso FROM pg_temp.integration_cupom").fetchone() == (
            "", "0000-00-00 00:00:00", "0000-00-00 00:00:00")

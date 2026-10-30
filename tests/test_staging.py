"""Verificações estáticas do manifesto de implantação STAGING."""

from src.config.settings import ROOT
from src.staging_deploy import PHASES
from src.staging_validate import CHECKS, duplicate_queries


def test_staging_manifest_is_complete_and_ordered():
    assert tuple(PHASES) == (1, 2, 3, 4, 5, 6, 7)
    paths = [path for phase in PHASES.values() for path in phase]
    assert len(paths) == 33  # schema + 13 views Magento + 19 views Ativo
    assert len(paths) == len(set(paths))
    assert all((ROOT / "sql" / "staging" / path).is_file() for path in paths)


def test_staging_scripts_only_define_staging_objects():
    for phase, names in PHASES.items():
        for name in names:
            sql = (ROOT / "sql" / "staging" / name).read_text(encoding="utf-8").lower()
            if phase == 1:
                assert "create schema if not exists staging" in sql
            else:
                assert "create or replace view staging." in sql
            assert "create table" not in sql
            assert "materialized view" not in sql
            assert "delete from raw." not in sql
            assert "update raw." not in sql
            assert "insert into raw." not in sql


def test_inscricao_views_do_not_join_one_to_many_ativo_entities():
    sql = (ROOT / "sql" / "staging" / "ativo" / "370_ativo_inscricao.sql").read_text(
        encoding="utf-8").lower()
    for table in ("ativo_pagamento", "ativo_transacao", "ativo_pedido_produto",
                  "ativo_endereco_pedido"):
        assert f"join staging.{table}" not in sql
    assert "from raw.ativo_pedido_evento" in sql


def test_every_view_has_documented_grain():
    for names in tuple(PHASES.values())[1:]:
        for name in names:
            sql = (ROOT / "sql" / "staging" / name).read_text(encoding="utf-8")
            assert "-- Grão:" in sql


def test_every_view_has_duplicate_validation():
    assert len(duplicate_queries("magento")) == CHECKS["magento"][1] == 14
    assert len(duplicate_queries("ativo")) == CHECKS["ativo"][1] == 18
    for system in CHECKS:
        assert all("group by" in sql.lower() and "having count(*) > 1" in sql.lower()
                   for sql in duplicate_queries(system))

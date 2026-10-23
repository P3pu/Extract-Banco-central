"""Invariantes de segurança sem qualquer conexão com bancos reais."""
from pathlib import Path
from unittest.mock import Mock
from contextlib import nullcontext
from datetime import date

import pytest

from src.core import runner


SQL = Path(__file__).resolve().parents[1] / "sql/core/v1"


@pytest.mark.parametrize("scope", runner.STEPS)
def test_steps_exist_and_do_not_write_sources(scope):
    for step in runner.STEPS[scope]:
        body = (SQL / step).read_text(encoding="utf-8").lower()
        assert "raw." not in body
        assert not any(term in body for term in
                       ("create table", "alter table", "drop table", "truncate"))
        assert "% (" not in body


@pytest.mark.parametrize("low,high", [(0, 99999), (5, 100004)])
def test_100000_inclusive_allowed(low, high):
    runner.validate_range(low, high)


@pytest.mark.parametrize("low,high", [(-1, 1), (2, 1), (0, 100000),
                                       (0, 9223372036854775808)])
def test_out_of_range_rejected(low, high):
    with pytest.raises(ValueError):
        runner.validate_range(low, high)


def test_production_guard(monkeypatch):
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = ("Atendimento",)
    monkeypatch.setenv("CORE_PG_DATABASE", "Atendimento")
    monkeypatch.delenv("CORE_PRODUCTION_APPROVAL", raising=False)
    with pytest.raises(RuntimeError, match="bloqueado"):
        runner.validate_destination(conn, approve_production=True)


def test_no_full_or_mysql_route():
    body = (Path(runner.__file__)).read_text(encoding="utf-8").lower()
    assert 'choices=("migrate", "run", "bulk-inscriptions")' in body
    assert "pymysql" not in body
    assert "--approve-production" in body
    assert "pg_try_advisory_lock" in body
    assert "with conn.transaction()" in body


def test_cache_is_session_only_and_reuses_staging_contracts():
    body = (Path(runner.__file__)).read_text(encoding="utf-8").lower()
    assert "create temp table" in body
    assert "on commit preserve rows" in body
    assert "create index on" in body
    assert "create unlogged table" not in body
    assert "create materialized view" not in body
    assert "set statement_timeout=60000" in body
    assert "pg_try_advisory_lock(21001,1)" in body
    assert not any("cpf" in query.lower() or "email" in query.lower()
                   for _, query, _ in runner.INSCRIPTION_CACHE)


def test_cached_sql_rewrites_only_the_intended_views():
    base = runner.inscription_sql("030_inscricao_base.sql", cached=True)
    mag = runner.inscription_sql("041_inscricao_magento.sql", cached=True)
    rec = runner.inscription_sql("050_reconciliacao_pedidos.sql", cached=True)
    assert "pg_temp.core_v1_magento_inscricao_cache" in base
    assert "pg_temp.core_v1_magento_bundle_componente_cache" in mag
    assert "pg_temp.core_v1_magento_bundle_pai_cache" in mag
    assert "pg_temp.core_v1_ativo_inscricao_pedido_cache" in rec
    assert "staging.ativo_inscricao" in runner.inscription_sql(
        "050_reconciliacao_pedidos.sql", cached=False)


def test_indicator_gate_stays_closed():
    migration = (SQL / "006_core_v1_extensions.sql").read_text(encoding="utf-8")
    assert "WHERE FALSE" in migration


def test_orphans_and_source_identity_are_not_dropped():
    base = (SQL / "030_inscricao_base.sql").read_text(encoding="utf-8")
    assert "LEFT JOIN core.fato_pedido" in base
    assert "LEFT JOIN core.evento_source_map" in base
    assert "inscricao_id BETWEEN" in base
    assert "pedido_id BETWEEN" not in base
    assert "NULL::bigint,NULL::text" in base  # Magento participante sem prova


def test_magento_header_discount_not_allocated_by_default():
    mag = (SQL / "041_inscricao_magento.sql").read_text(encoding="utf-8")
    assert "desconto_conciliado" in mag
    assert "d.desconto_conciliado" in mag
    assert "d.qtd_segura" in mag
    assert "staging.magento_bundle_componente" in mag
    assert "categoria_origem ILIKE" not in mag


def test_ativo_tax_and_kit_are_distinct():
    ativo = (SQL / "040_inscricao_ativo.sql").read_text(encoding="utf-8")
    assert "taxa_servico_ativo=d.taxa" in ativo
    assert "valor_kit_ativo=d.valor_kit" in ativo
    assert "GREATEST(0,d.preco-d.desconto_num-d.valor_kit)" in ativo
    assert "classificacao_cupom_ativo=NULL" in ativo


def test_invalidation_and_dependency_hash_cover_auxiliary_sources():
    assert "022_invalidate_order_dependents.sql" in runner.STEPS["orders"]
    assert "013_invalidate_event_dependents.sql" in runner.STEPS["events"]
    assert "014_invalidate_combo_dependents.sql" in runner.STEPS["combos"]
    for name in ("040_inscricao_ativo.sql", "041_inscricao_magento.sql"):
        body = (SQL / name).read_text(encoding="utf-8")
        assert "dependencias_hash_snapshot" in body
        assert "%(as_of_date)s" in body


def test_compose_is_local_and_volume_unique():
    body = (Path(__file__).resolve().parents[1] /
            "homologation/core-v1/compose.yaml").read_text(encoding="utf-8")
    assert "127.0.0.1:15439:5432" in body
    assert "core_v1_pgdata" in body
    assert "core_c1_pgdata" not in body
    assert "/var/run/docker.sock" not in body


def test_failure_is_audited_and_never_marked_success(monkeypatch):
    conn = Mock()
    conn.transaction.side_effect = lambda: nullcontext()
    conn.execute.side_effect = lambda sql, params=None: (
        Mock(fetchone=lambda: (True,), rowcount=0)
        if "pg_try_advisory_lock" in sql else
        (_ for _ in ()).throw(RuntimeError("SCHEMA_DIVERGENTE: synthetic"))
        if "010_eventos.sql" in sql else Mock(rowcount=0)
    )
    monkeypatch.setattr(runner, "schema_contract", lambda *args: None)
    monkeypatch.setattr(runner, "unique_source_grain", lambda *args: None)
    monkeypatch.setattr(runner, "STEPS", {"events": ("010_eventos.sql",)})
    # O teste usa falha no arquivo SQL via Path.read_text em vez de mockar PG.
    monkeypatch.setattr(Path, "read_text", lambda self, **kwargs:
                        "010_eventos.sql" if self.name == "010_eventos.sql" else "")
    with pytest.raises(RuntimeError, match="SCHEMA_DIVERGENTE"):
        runner.run_range(conn, "events", 0, 10, date(2026, 10, 22))
    statements = [str(call.args[0]) for call in conn.execute.call_args_list]
    assert any("status='FAILED'" in query for query in statements)
    assert not any("status='SUCCEEDED'" in query for query in statements)

"""Asserções sobre o banco sintético, nunca sobre Atendimento.

Rodar apenas após os comandos do homologation/core-v1/README.md.
"""
from decimal import Decimal
import os
from pathlib import Path

import psycopg
import pytest
from src.core import runner
from datetime import date


pytestmark = pytest.mark.skipif(os.environ.get("CORE_V1_LAB_TEST") != "1",
                                reason="laboratório CORE V1 não habilitado")


@pytest.fixture(scope="module")
def db():
    assert os.environ.get("CORE_PG_DATABASE") == "core_v1_homolog"
    assert os.environ.get("CORE_PG_HOST") in ("127.0.0.1", "localhost")
    with psycopg.connect(
        host=os.environ["CORE_PG_HOST"], port=os.environ["CORE_PG_PORT"],
        dbname=os.environ["CORE_PG_DATABASE"], user=os.environ["CORE_PG_USER"],
        password=os.environ["CORE_PG_PASSWORD"], sslmode="disable",
        autocommit=True,
    ) as connection:
        assert connection.execute("SELECT current_database()").fetchone()[0] == "core_v1_homolog"
        yield connection


def one(db, query, *params):
    row = db.execute(query, params).fetchone()
    assert row is not None
    return row


def test_magento_header_and_item_finance(db):
    assert one(db, "SELECT valor_bruto_pedido,desconto_pedido_origem,"
               "valor_liquido_pedido FROM core.fato_pedido "
               "WHERE origem='magento' AND pedido_id_origem=3001") == (
                   Decimal("100.0000"), Decimal("-15.0000"), Decimal("85.0000"))
    assert one(db, "SELECT desconto_filhos_magento,valor_liquido_inscricao "
               "FROM core.fato_inscricao WHERE origem='magento' "
               "AND inscricao_id_origem=4001") == (
                   Decimal("15.0000"), Decimal("85.0000"))


def test_header_only_discount_is_not_allocated(db):
    assert one(db, "SELECT desconto_nao_atribuido FROM core.fato_pedido "
               "WHERE origem='magento' AND pedido_id_origem=3010")[0] == Decimal("20.0000")
    assert one(db, "SELECT valor_liquido_inscricao,flag_excecao_financeira "
               "FROM core.fato_inscricao WHERE origem='magento' "
               "AND inscricao_id_origem=4101") == (None, True)


@pytest.mark.parametrize("item_id", [4201, 4301, 4401, 4501])
def test_partial_cancel_refund_or_quantity_is_not_invented(db, item_id):
    assert one(db, "SELECT valor_liquido_inscricao FROM core.fato_inscricao "
               "WHERE origem='magento' AND inscricao_id_origem=%s", item_id)[0] is None


def test_ativo_tax_kit_null_and_orphan(db):
    assert one(db, "SELECT valor_kit_ativo,taxa_servico_ativo,"
               "valor_liquido_inscricao,valor_bruto_mais_taxa_derivado "
               "FROM core.fato_inscricao WHERE origem='ativo' "
               "AND inscricao_id_origem=5001") == (
                   Decimal("5.0000"), Decimal("2.0000"),
                   Decimal("85.0000"), Decimal("102.0000"))
    assert one(db, "SELECT flag_pedido_nao_encontrado,pedido_key "
               "FROM core.fato_inscricao WHERE origem='ativo' "
               "AND inscricao_id_origem=5002") == (True, None)
    assert one(db, "SELECT valor_kit_ativo,valor_liquido_inscricao "
               "FROM core.fato_inscricao WHERE origem='ativo' "
               "AND inscricao_id_origem=5004") == (None, None)


def test_grains_and_gate(db):
    assert one(db, "SELECT count(*) FROM core.fato_inscricao "
               "WHERE origem='magento' AND inscricao_id_origem=4001")[0] == 1
    assert one(db, "SELECT count(*) FROM core.fato_inscricao_indicadores_validos")[0] == 0
    assert one(db, "SELECT count(*) FROM core.fato_inscricao "
               "WHERE origem='magento' AND inscricao_id_origem IN (4002,4003)")[0] == 0


def test_same_order_id_two_sources_and_cancelled_registration(db):
    assert one(db, "SELECT count(*) FROM core.fato_pedido "
               "WHERE pedido_id_origem=3001")[0] == 2
    assert one(db, "SELECT flag_cancelado_inscricao,contabiliza_inscricao "
               "FROM core.fato_inscricao WHERE origem='ativo' "
               "AND inscricao_id_origem=5006") == (True, False)
    assert one(db, "SELECT count(*) FROM core.fato_inscricao "
               "WHERE origem='ativo' AND pedido_id_origem=3001")[0] == 3


def test_balcony_eligible_but_not_confirmed(db):
    assert one(db, "SELECT pedido_elegivel,pagamento_confirmado "
               "FROM core.fato_pedido WHERE origem='ativo' "
               "AND pedido_id_origem=3003") == (True, False)
    assert one(db, "SELECT contabiliza_inscricao,pagamento_confirmado "
               "FROM core.fato_inscricao WHERE origem='ativo' "
               "AND inscricao_id_origem=5007") == (True, False)


def test_special_status_group_precedence_and_courtesy(db):
    assert one(db, "SELECT status_pendente_validacao,contabiliza_inscricao "
               "FROM core.fato_inscricao WHERE origem='ativo' "
               "AND inscricao_id_origem=5008") == (True, None)
    assert one(db, "SELECT classificacao_comercial FROM core.fato_inscricao "
               "WHERE origem='ativo' AND inscricao_id_origem=5009")[0] == "GRUPOS"
    assert one(db, "SELECT classificacao_comercial FROM core.fato_inscricao "
               "WHERE origem='ativo' AND inscricao_id_origem=5010")[0] == "CORTESIA"


def test_events_with_same_sku_remain_distinct(db):
    assert one(db, "SELECT count(*) FROM core.dim_evento "
               "WHERE sku_referencia='SYN-EVENT'")[0] == 2
    assert one(db, "SELECT count(DISTINCT evento_key) FROM core.dim_evento "
               "WHERE sku_referencia='SYN-EVENT'")[0] == 2


def test_mixed_future_past_payment(db):
    assert one(db, "SELECT flag_pedido_misto_temporal FROM core.fato_pedido "
               "WHERE origem='magento' AND pedido_id_origem=3070")[0] is True
    assert one(db, "SELECT pagamento_presumido,pagamento_confirmado "
               "FROM core.fato_inscricao WHERE origem='magento' "
               "AND inscricao_id_origem=4701") == (True, False)
    assert one(db, "SELECT pagamento_presumido,pagamento_confirmado "
               "FROM core.fato_inscricao WHERE origem='magento' "
               "AND inscricao_id_origem=4703") == (False, False)


def test_idempotence_and_temporal_rederivation():
    with psycopg.connect(
        host=os.environ["CORE_PG_HOST"], port=os.environ["CORE_PG_PORT"],
        dbname=os.environ["CORE_PG_DATABASE"], user=os.environ["CORE_PG_USER"],
        password=os.environ["CORE_PG_PASSWORD"], sslmode="disable",
        autocommit=True,
    ) as conn:
        runner.validate_destination(conn, False)
        before = conn.execute("SELECT count(*) FROM core.fato_inscricao").fetchone()[0]
        runner.run_range(conn, "inscriptions", 0, 10000, date(2026, 10, 22))
        assert conn.execute("SELECT count(*) FROM core.fato_inscricao").fetchone()[0] == before
        runner.run_range(conn, "inscriptions", 0, 10000, date(2024, 10, 22))
        assert conn.execute("SELECT pagamento_presumido FROM core.fato_inscricao "
                            "WHERE origem='magento' AND inscricao_id_origem=4701")\
                   .fetchone()[0] is False
        runner.run_range(conn, "inscriptions", 0, 10000, date(2026, 10, 22))
        assert conn.execute("SELECT pagamento_presumido FROM core.fato_inscricao "
                            "WHERE origem='magento' AND inscricao_id_origem=4701")\
                   .fetchone()[0] is True


def test_source_protocols_and_no_person_unification(db):
    assert one(db, "SELECT protocolo FROM core.fato_pedido "
               "WHERE origem='ativo' AND pedido_id_origem=3001")[0] == "3001"
    assert one(db, "SELECT protocolo FROM core.fato_pedido "
               "WHERE origem='magento' AND pedido_id_origem=3001")[0] == "SYN-M-3001"
    assert one(db, "SELECT count(*) FROM core.dim_pessoa")[0] == 0


def test_participant_namespace_and_magento_null(db):
    assert one(db, "SELECT participante_id_origem,participante_namespace_origem "
               "FROM core.fato_inscricao WHERE origem='ativo' "
               "AND inscricao_id_origem=5005") == (7005, "Usuario")
    assert one(db, "SELECT participante_id_origem FROM core.fato_inscricao "
               "WHERE origem='magento' AND inscricao_id_origem=4001")[0] is None


def test_magento_numeric_category_not_textual_classification(db):
    assert one(db, "SELECT categoria_id_origem,classificacao_comercial "
               "FROM core.fato_inscricao WHERE origem='magento' "
               "AND inscricao_id_origem=4001") == ("1", "SITE")


def test_combo_without_proven_composition_remains_partial(db):
    assert one(db, "SELECT qtd_inscricoes_previstas,flag_composicao_validada "
               "FROM core.dim_combo WHERE origem='ativo' "
               "AND combo_id_origem='2001'") == (None, False)
    assert one(db, "SELECT count(*) FROM core.combo_inscricao_atribuicao")[0] == 0


def test_combo_incomplete_and_complete_only_after_manual_attribution(db):
    sql = (Path(runner.__file__).resolve().parents[2] /
           "sql/core/v1/910_combo_candidate_readonly.sql").read_text(encoding="utf-8")
    query = "WITH por_grupo AS" + sql.split("WITH por_grupo AS", 1)[1].split("ROLLBACK;", 1)[0]

    class RollbackCase(Exception):
        pass

    try:
        with db.transaction():
            db.execute("UPDATE core.dim_combo SET qtd_inscricoes_previstas=5,"
                       "flag_composicao_validada=true "
                       "WHERE origem='ativo' AND combo_id_origem='2001'")
            db.execute("INSERT INTO core.combo_inscricao_atribuicao "
                       "(inscricao_key,combo_key,grupo_comercial_id,validado_por,validado_em) "
                       "SELECT inscricao_key,combo_key,'SYN-ONE','synthetic-review',"
                       "clock_timestamp() FROM core.fato_inscricao "
                       "WHERE origem='ativo' AND inscricao_id_origem BETWEEN 5011 AND 5014")
            assert db.execute(query).fetchone()[4:] == (False, None)
            db.execute("INSERT INTO core.combo_inscricao_atribuicao "
                       "(inscricao_key,combo_key,grupo_comercial_id,validado_por,validado_em) "
                       "SELECT inscricao_key,combo_key,'SYN-ONE','synthetic-review',"
                       "clock_timestamp() FROM core.fato_inscricao "
                       "WHERE origem='ativo' AND inscricao_id_origem=5015")
            assert db.execute(query).fetchone()[4:] == (True, Decimal("475.0000"))
            raise RollbackCase()
    except RollbackCase:
        pass


def test_failure_mid_batch_rolls_back_and_audits():
    with psycopg.connect(
        host=os.environ["CORE_PG_HOST"], port=os.environ["CORE_PG_PORT"],
        dbname=os.environ["CORE_PG_DATABASE"], user=os.environ["CORE_PG_USER"],
        password=os.environ["CORE_PG_PASSWORD"], sslmode="disable",
        autocommit=True,
    ) as conn:
        runner.validate_destination(conn, False)
        before = conn.execute("SELECT derivado_em FROM core.fato_inscricao "
                              "WHERE origem='ativo' AND inscricao_id_origem=5011").fetchone()[0]
        conn.execute("DROP TRIGGER IF EXISTS _synthetic_fail ON core.fato_inscricao")
        conn.execute("DROP FUNCTION IF EXISTS core._synthetic_fail()")
        conn.execute("CREATE FUNCTION core._synthetic_fail() RETURNS trigger "
                     "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic_failure'; END $$")
        conn.execute("CREATE TRIGGER _synthetic_fail BEFORE UPDATE ON core.fato_inscricao "
                     "FOR EACH ROW EXECUTE FUNCTION core._synthetic_fail()")
        try:
            with pytest.raises(psycopg.Error):
                runner.run_range(conn, "inscriptions", 0, 10000, date(2028, 10, 22))
        finally:
            conn.execute("DROP TRIGGER _synthetic_fail ON core.fato_inscricao")
            conn.execute("DROP FUNCTION core._synthetic_fail()")
        after = conn.execute("SELECT derivado_em FROM core.fato_inscricao "
                             "WHERE origem='ativo' AND inscricao_id_origem=5011").fetchone()[0]
        assert after == before
        assert conn.execute("SELECT count(*) FROM core.core_etl_execucao "
                            "WHERE status='FAILED' AND limite_inferior=0 "
                            "AND limite_superior=10000").fetchone()[0] >= 1

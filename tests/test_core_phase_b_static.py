"""Guardas estáticos dos SQL propostos; não conecta a nenhum banco."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql" / "core" / "proposed"


def read(name: str) -> str:
    return (SQL / name).read_text(encoding="utf-8")


class CorePhaseBStaticTests(unittest.TestCase):
    def test_basic_upsert_preserves_derived_columns(self):
        source = read("005_core_inscricao_base_upsert.sql")
        update = source.split("ON CONFLICT (origem,inscricao_id_origem) DO UPDATE SET", 1)[1]
        update = update.split("WHERE core.fato_inscricao.conteudo_hash", 1)[0]
        for column in (
            "classificacao_venda", "motivo_classificacao",
            "valor_liquido_inscricao", "valor_liquido_itens",
            "desconto_aplicado_inscricao", "flag_excecao_financeira",
            "pagamento_confirmado", "pagamento_presumido", "pago_considerado",
            "derivado_de_hash", "derivado_em",
        ):
            self.assertNotRegex(update, rf"\b{column}\s*=", column)
        self.assertIn("estado_derivacao='PENDENTE'", update)

    def test_publication_requires_current_derivation(self):
        ddl = read("001_core_ddl.sql")
        self.assertIn("derivado_de_hash = conteudo_hash", ddl)
        self.assertIn("estado_derivacao = 'VALIDADO'", ddl)
        self.assertIn("fato_inscricao_derivacao_checagem", ddl)
        self.assertIn("America/Sao_Paulo", ddl)

    def test_all_batch_sql_uses_pgadmin_compatible_helpers(self):
        for name in (
            "003_core_upserts.sql", "004_core_inscricao_candidates.sql",
            "005_core_inscricao_base_upsert.sql",
        ):
            source = read(name)
            self.assertNotRegex(source, r":id_(?:min|max)\b", name)
            self.assertIn("core.batch_min()", source)
            self.assertIn("core.batch_max()", source)
        helpers = read("002_core_helpers.sql")
        self.assertIn("maximo - minimo > 100000", helpers)

    def test_status_and_classification_precedence(self):
        helpers = read("002_core_helpers.sql")
        status = helpers.split("FUNCTION core.magento_status_corporativo", 1)[1]
        status = status.split("FUNCTION core.magento_pagamento_confirmado", 1)[0]
        self.assertLess(status.index("e = 'canceled' OR s = 'canceled'"),
                        status.index("THEN 'CONFIRMADO'"))
        self.assertRegex(status, r"e IN \('processing','approved','complete'\)\s+AND s IN")
        classificacao = helpers.split("FUNCTION core.classificacao_ativo", 1)[1]
        classificacao = classificacao.split("FUNCTION core.classificacao_magento", 1)[0]
        self.assertLess(classificacao.index("classificacao_cupom ILIKE '%grupos%'"),
                        classificacao.index("tem_cabecalho_cupom IS NOT TRUE"))
        self.assertLess(classificacao.index("tem_cabecalho_cupom IS NOT TRUE"),
                        classificacao.index("THEN 'Cortesia'"))

    def test_no_free_text_pii_in_quality_tables(self):
        ddl = read("001_core_ddl.sql")
        pessoa = ddl.split("CREATE TABLE core.dim_pessoa", 1)[1].split(");", 1)[0]
        alerta = ddl.split("CREATE TABLE core.core_alerta_qualidade", 1)[1].split(");", 1)[0]
        execucao = ddl.split("CREATE TABLE core.core_etl_execucao", 1)[1].split(");", 1)[0]
        self.assertIn("cpf_token_seguro BYTEA", pessoa)
        self.assertIn("octet_length(cpf_token_seguro) = 32", pessoa)
        self.assertIn("identificador_origem BIGINT", alerta)
        self.assertNotRegex(alerta, r"\bmensagem\s+TEXT\b")
        self.assertNotRegex(execucao, r"\berro_resumido\s+TEXT\b")
        self.assertIn("codigo_regra TEXT NOT NULL CHECK", alerta)
        self.assertIn("REVOKE ALL ON core.dim_pessoa, core.pessoa_source_map FROM PUBLIC", ddl)

    def test_acceptance_covers_regressions(self):
        acceptance = read("900_core_acceptance_readonly.sql")
        for marker in ("-- B01:", "-- B02:", "-- B03:", "-- B04:", "-- B05:"):
            self.assertIn(marker, acceptance)
        self.assertIn("'new','approved'", acceptance)
        self.assertIn("'Grupos','Cortesia'", acceptance)
        self.assertIn("-- B06:", acceptance)
        self.assertIn("core.magento_status_alerta", read("003_core_upserts.sql"))


if __name__ == "__main__":
    unittest.main()

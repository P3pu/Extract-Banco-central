"""Guardas estáticos dos SQL propostos; não conecta a nenhum banco."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql" / "core" / "proposed"


def read(name: str) -> str:
    return (SQL / name).read_text(encoding="utf-8")


def select_columns(select_sql: str) -> list[str]:
    """Separa expressões SELECT no nível superior (inclusive NUMERIC(20,4))."""
    columns, start, depth, quoted = [], 0, 0, False
    for position, char in enumerate(select_sql):
        if char == "'":
            quoted = not quoted
        elif not quoted:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                columns.append(select_sql[start:position].strip())
                start = position + 1
    columns.append(select_sql[start:].strip())
    return columns


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
        self.assertIn("derivado_de_dependencias_hash IS NOT NULL", ddl)
        self.assertIn("America/Sao_Paulo", ddl)
        view = ddl.split("CREATE VIEW core.fato_inscricao_indicadores_validos AS", 1)[1]
        view = view.split("COMMIT;", 1)[0]
        self.assertRegex(view, r"\bWHERE FALSE\b")
        self.assertIn("derivado_de_dependencias_hash = dependencias_hash_snapshot", view)
        self.assertIn("versao_regras_derivacao IS NOT NULL", view)

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
        self.assertIn("maximo - minimo >= 100000", helpers)
        self.assertIn("BETWEEN inclui as duas extremidades", helpers)

    def test_status_and_classification_precedence(self):
        helpers = read("002_core_helpers.sql")
        status = helpers.split("FUNCTION core.magento_status_corporativo", 1)[1]
        status = status.split("FUNCTION core.magento_pagamento_confirmado", 1)[0]
        self.assertLess(status.index("e = 'canceled' OR s = 'canceled'"),
                        status.index("THEN 'CONFIRMADO'"))
        self.assertRegex(status, r"e IN \('processing','approved','complete'\)\s+AND s IN")
        classificacao = helpers.split("FUNCTION core.classificacao_ativo", 1)[1]
        classificacao = classificacao.split("FUNCTION core.classificacao_magento", 1)[0]
        self.assertLess(classificacao.index("core.cupom_ativo_e_grupos(classificacao_cupom)"),
                        classificacao.index("tem_cabecalho_cupom IS NOT TRUE"))
        self.assertLess(classificacao.index("tem_cabecalho_cupom IS NOT TRUE"),
                        classificacao.index("THEN 'Cortesia'"))
        exact = helpers.split("FUNCTION core.cupom_ativo_e_grupos", 1)[1]
        exact = exact.split("FUNCTION core.classificacao_ativo", 1)[0]
        self.assertIn("BTRIM(classificacao)", exact)
        self.assertIn("'[[:space:]]+'", exact)
        self.assertRegex(exact, r"= 'grupos'")
        self.assertNotIn("ILIKE", exact)
        self.assertIn("core.cupom_ativo_e_grupos(cab.classificacao)",
                      read("004_core_inscricao_candidates.sql"))

    def test_union_has_explicit_target_types_in_both_sources(self):
        source = read("005_core_inscricao_base_upsert.sql")
        body = source.split("WITH fonte AS MATERIALIZED (", 1)[1]
        body = body.split("), pronta AS (", 1)[0]
        branches = body.split("UNION ALL")
        self.assertEqual(len(branches), 2)
        expected = (
            "TEXT", "BIGINT", "BIGINT", "BIGINT", "BIGINT", "BIGINT",
            "BIGINT", "BIGINT", "DATE", "TEXT", "TEXT", "TEXT", "TEXT",
            "TEXT", "TEXT", "TEXT", "TEXT", "TEXT", "TEXT", "INTEGER",
            "NUMERIC(20,4)", "TEXT", "NUMERIC(20,4)", "BOOLEAN", "BOOLEAN",
            "BOOLEAN", "UUID",
        )
        for branch in branches:
            select = branch.split("SELECT ", 1)[1].split("\n    FROM staging.", 1)[0]
            columns = select_columns(select)
            self.assertEqual(len(columns), len(expected))
            for position, (column, target) in enumerate(zip(columns, expected), 1):
                self.assertRegex(column, rf"::{re.escape(target)}(?:\s+AS\s+\w+)?\s*$",
                                 f"coluna {position}: {column}")
        self.assertIn("i.usuario_id::BIGINT AS participante_id_origem", branches[0])
        self.assertIn("NULL::BIGINT, NULL::BIGINT, i.data_evento::DATE", branches[1])

    def test_ativo_buyer_is_null_until_source_exists(self):
        ativo_view = (ROOT / "sql" / "staging" / "ativo" /
                      "200_ativo_pedido.sql").read_text(encoding="utf-8")
        self.assertNotIn("comprador_usuario_id", ativo_view)
        ativo_upsert = read("003_core_upserts.sql").split("-- ETAPA 2B:", 1)[1]
        self.assertIn("p.codigo, NULL::BIGINT", ativo_upsert)
        self.assertNotIn("p.comprador_usuario_id", ativo_upsert)
        self.assertNotIn("i.usuario_id", ativo_upsert)
        update = ativo_upsert.split("ON CONFLICT (origem, pedido_id_origem) DO UPDATE SET", 1)[1]
        update = update.split("WHERE core.fato_pedido.conteudo_hash", 1)[0]
        self.assertNotRegex(update, r"\bcomprador_id_origem\s*=")

    def test_dependency_only_changes_remain_unpublished(self):
        ddl = read("001_core_ddl.sql")
        view = ddl.split("CREATE VIEW core.fato_inscricao_indicadores_validos AS", 1)[1]
        self.assertRegex(view, r"\bWHERE FALSE\b")
        for field in ("dependencias_hash_snapshot TEXT",
                      "derivado_de_dependencias_hash TEXT",
                      "versao_regras_derivacao TEXT"):
            self.assertIn(field, ddl)
        docs = (ROOT / "docs" / "CORE_FASE_B_MODELO.md").read_text(encoding="utf-8")
        for dependency in ("state/status", "canceladas/reembolsadas",
                           "filhos/pais/cabeçalho", "classificação/código de cupom",
                           "categoria/valor de kit", "cadastros e regras auxiliares",
                           "INSERT/UPDATE/DELETE", "versão de regra"):
            self.assertIn(dependency, docs)
        acceptance = read("900_core_acceptance_readonly.sql")
        self.assertIn("-- B07:", acceptance)
        self.assertIn("-- B08:", acceptance)

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
        self.assertIn("Supergrupos", acceptance)
        self.assertIn("[1,100001] rejeita", acceptance)
        self.assertIn("core.magento_status_alerta", read("003_core_upserts.sql"))


if __name__ == "__main__":
    unittest.main()

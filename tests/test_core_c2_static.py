"""Verificações locais C2.1; nunca conecta ao PostgreSQL."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "sql" / "core" / "diagnostics"
EXPECTED = {
    "c2_magento_header_readonly.sql",
    "c2_magento_items_plan_readonly.sql",
    "c2_magento_items_after_plan_readonly.sql",
    "c2_ativo_range_plan_readonly.sql",
    "c2_ativo_range_after_plan_readonly.sql",
    "c2_quality_catalog_readonly.sql",
    "c2_quality_plan_readonly.sql",
    "c2_quality_after_plan_readonly.sql",
}


class CoreC2StaticTests(unittest.TestCase):
    def test_all_diagnostics_are_read_only_and_fail_closed(self):
        self.assertEqual({p.name for p in DIAG.glob("*.sql")}, EXPECTED)
        forbidden = re.compile(
            r"\b(?:INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|COPY|"
            r"VACUUM|ANALYZE|CALL|DO|GRANT|REVOKE)\b", re.I
        )
        for path in DIAG.glob("*.sql"):
            with self.subTest(path=path.name):
                sql = path.read_text(encoding="utf-8")
                body = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
                self.assertEqual(body.count("BEGIN READ ONLY;"), 1)
                self.assertEqual(body.count("COMMIT;"), 1)
                self.assertIn("SET LOCAL statement_timeout", body)
                self.assertIn("SET LOCAL lock_timeout", body)
                self.assertIn("current_database() = 'Atendimento'", body)
                self.assertIn("current_setting('transaction_read_only') = 'on'", body)
                self.assertNotRegex(body, forbidden)
                self.assertNotRegex(body, r"(?i)\bcore\.[a-z_]+")
                self.assertNotIn("EXPLAIN ANALYZE", body.upper())
                self.assertNotRegex(body, r"(?i)\b(?:cpf|email|e_mail|documento)\b")
                self.assertNotRegex(body, r"(?i)\b(?:raw\.ativo_usuario|raw\.magento_customer)\b")

    def test_ranges_are_unset_and_small_until_explicitly_edited(self):
        paths = [DIAG / name for name in (
            "c2_ativo_range_plan_readonly.sql",
            "c2_ativo_range_after_plan_readonly.sql",
            "c2_quality_plan_readonly.sql",
            "c2_quality_after_plan_readonly.sql",
        )]
        for path in paths:
            with self.subTest(path=path.name):
                sql = path.read_text(encoding="utf-8")
                self.assertIn("SET LOCAL c2.ativo_id_min = 'UNSET';", sql)
                self.assertIn("SET LOCAL c2.ativo_id_max = 'UNSET';", sql)
                self.assertRegex(
                    sql,
                    r"current_setting\('c2\.ativo_id_max'\)::BIGINT\s*"
                    r"- current_setting\('c2\.ativo_id_min'\)::BIGINT < 1000",
                )
                self.assertIn("destino_e_intervalo_validados", sql)

    def test_versioned_staging_fields_match_diagnostics(self):
        views = {
            "magento_pedido": "sql/staging/magento/020_magento_pedido.sql",
            "magento_item_pedido": "sql/staging/magento/030_magento_item_pedido.sql",
            "ativo_inscricao": "sql/staging/ativo/370_ativo_inscricao.sql",
            "ativo_pagamento": "sql/staging/ativo/280_ativo_pagamento.sql",
            "ativo_categoria": "sql/staging/ativo/230_ativo_categoria.sql",
        }
        for name, source in views.items():
            self.assertIn("CREATE OR REPLACE VIEW staging." + name,
                          (ROOT / source).read_text(encoding="utf-8"))
        self.assertIn("discount_amount AS desconto",
                      (ROOT / views["magento_pedido"]).read_text(encoding="utf-8"))
        self.assertIn("qty_refunded AS quantidade_reembolsada",
                      (ROOT / views["magento_item_pedido"]).read_text(encoding="utf-8"))
        self.assertIn("i.nr_taxa AS taxa",
                      (ROOT / views["ativo_inscricao"]).read_text(encoding="utf-8"))
        self.assertIn("vl_kit AS valor_kit",
                      (ROOT / views["ativo_categoria"]).read_text(encoding="utf-8"))

    def test_plan_files_are_explain_only_after_guard(self):
        counts = {
            "c2_magento_items_plan_readonly.sql": 1,
            "c2_ativo_range_plan_readonly.sql": 1,
            "c2_quality_plan_readonly.sql": 4,
        }
        for name, expected in counts.items():
            with self.subTest(name=name):
                sql = (DIAG / name).read_text(encoding="utf-8")
                self.assertEqual(sql.count("EXPLAIN (FORMAT TEXT, COSTS TRUE)"), expected)
                self.assertLess(sql.index("destino_"), sql.index("EXPLAIN ("))

    def test_matrix_is_unobserved_and_gate_remains_closed(self):
        matrix = (ROOT / "docs" / "CORE_FASE_C2_MATRIZ.md").read_text(encoding="utf-8")
        self.assertIn("Valor observado", matrix)
        self.assertGreaterEqual(matrix.count("NAO_COBERTO"), 20)
        self.assertNotIn("| APROVADO |", matrix)
        ddl = (ROOT / "sql" / "core" / "proposed" / "001_core_ddl.sql").read_text(encoding="utf-8")
        self.assertIn("WHERE FALSE", ddl)


if __name__ == "__main__":
    unittest.main()

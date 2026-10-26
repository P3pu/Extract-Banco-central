"""RAW R1: somente verificações textuais locais, sem conexão ao banco."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "sql" / "postgres" / "migrations"
LAB = ROOT / "homologation" / "raw-index-r1"
PREFIX = "001_idx_magento_item_order_id"


def sql(name: str) -> str:
    return (MIGRATIONS / name).read_text(encoding="utf-8")


def executable_sql(text: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


class RawIndexR1StaticTests(unittest.TestCase):
    def test_migration_is_one_concurrent_autocommit_statement(self):
        body = executable_sql(sql(PREFIX + ".sql")).strip()
        self.assertEqual(body.count(";"), 1)
        self.assertRegex(
            body,
            r"(?is)^CREATE\s+INDEX\s+CONCURRENTLY\s+IF\s+NOT\s+EXISTS\s+"
            r"idx_magento_sales_order_item_order_id\s+ON\s+"
            r"raw\.magento_sales_order_item\s+USING\s+btree\s*\(order_id\);$",
        )
        self.assertNotRegex(body, r"(?i)\b(?:BEGIN|DROP|ALTER|INSERT|UPDATE|DELETE)\b")

    def test_preflight_and_verification_fail_closed_on_catalog(self):
        for suffix in ("_preflight.sql", "_verify.sql"):
            with self.subTest(suffix=suffix):
                body = executable_sql(sql(PREFIX + suffix))
                for fragment in (
                    "BEGIN READ ONLY;", "SET LOCAL statement_timeout",
                    "SET LOCAL lock_timeout", "pg_index", "pg_class",
                    "pg_am", "pg_opclass", "am.amname='btree'",
                    "x.indkey[0]=c.attnum", "x.indnkeyatts=1",
                    "x.indnatts=1", "x.indoption[0]=0",
                    "x.indpred IS NULL", "x.indexprs IS NULL",
                    "x.indisvalid AND x.indisready AND x.indislive",
                    "IS DISTINCT FROM a.indice_oid", "1 / CASE",
                ):
                    self.assertIn(fragment, body)
                self.assertNotRegex(
                    body, r"(?i)\b(?:CREATE|DROP|ALTER|INSERT|UPDATE|DELETE)\b"
                )
                self.assertEqual(body.count("BEGIN READ ONLY;"), 1)
                self.assertEqual(body.count("COMMIT;"), 1)

    def test_production_diagnostics_are_read_only_and_bounded(self):
        for suffix in ("_diagnostics_readonly.sql", "_explain_readonly.sql"):
            with self.subTest(suffix=suffix):
                body = executable_sql(sql(PREFIX + suffix))
                self.assertIn("BEGIN READ ONLY;", body)
                self.assertIn("current_database()='Atendimento'", body)
                self.assertIn("current_setting('transaction_read_only')='on'", body)
                self.assertIn("statement_timeout = '5s'", body)
                self.assertIn("lock_timeout = '500ms'", body)
                self.assertNotRegex(
                    body, r"(?i)\b(?:CREATE|DROP|ALTER|INSERT|UPDATE|DELETE|ANALYZE)\b"
                )
        explain = sql(PREFIX + "_explain_readonly.sql")
        self.assertIn("EXPLAIN (FORMAT TEXT, COSTS TRUE)", explain)
        self.assertIn("166688,1673612,1673646,1673884", explain)
        self.assertNotIn("EXPLAIN ANALYZE", explain.upper())
        diagnostics = sql(PREFIX + "_diagnostics_readonly.sql")
        for fragment in ("pg_stat_progress_create_index", "pg_table_size",
                         "pg_indexes_size", "pg_total_relation_size",
                         "pg_stat_user_tables", "indisvalid", "indisready"):
            self.assertIn(fragment, diagnostics)

    def test_lab_is_new_isolated_project_and_no_production_mount(self):
        compose = (LAB / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("name: banco-central-raw-r1", compose)
        self.assertIn("image: postgres:16.13-trixie", compose)
        self.assertIn("network_mode: none", compose)
        self.assertIn("profiles: [manual]", compose)
        self.assertIn("raw_r1_pgdata:/var/lib/postgresql/data", compose)
        self.assertNotRegex(compose, r"(?m)^\s*ports\s*:")
        self.assertNotIn("core_c1_pgdata", compose)
        for mount in (
            "003b_create_magento_sales_order_item.sql:/workspace/contract.sql:ro",
            "/workspace/migrations:ro", "/workspace/r1:ro",
        ):
            self.assertIn(mount, compose)
        self.assertNotRegex(compose, r"(?i)(178\.156\.|rds\.amazonaws|naruto|Atendimento)")

    def test_lab_runner_validates_destination_and_separates_concurrent_ddl(self):
        runner = (LAB / "run.sh").read_text(encoding="utf-8")
        self.assertIn("raw_r1_homolog:raw_r1:true:160013", runner)
        self.assertIn("inet_server_addr() IS NULL", runner)
        self.assertIn("assert_local\n  psql_local -f", runner)
        self.assertIn("assert_fresh_schema", runner)
        self.assertIn("-v AUTOCOMMIT=on -f", runner)
        executable = "\n".join(line for line in runner.splitlines()
                               if not line.lstrip().startswith("#"))
        self.assertNotIn("--single-transaction", executable)
        self.assertNotRegex(runner, r"(?i)\bdrop\b|down --volumes|volume rm")
        self.assertIn("if [ \"$before\" != \"$after\" ]; then", runner)
        self.assertIn("_preflight.sql", runner)
        self.assertIn("_verify.sql", runner)

    def test_fixtures_are_synthetic_and_index_not_in_raw_loader(self):
        seed = (LAB / "seed.sql").read_text(encoding="utf-8")
        tests = (LAB / "tests.psql").read_text(encoding="utf-8")
        self.assertIn("synthetic-r1", seed)
        self.assertIn("800000001", seed)
        self.assertIn("INSERT INTO raw.magento_sales_order_item", tests)
        self.assertIn("UPDATE raw.magento_sales_order_item", tests)
        self.assertIn("WHERE order_id=800000003", tests)
        self.assertNotRegex(seed + tests, r"(?i)\b(?:cpf|email|e_mail|documento)\b")
        # O carregador legado seleciona apenas arquivos numerados na raiz,
        # nunca em sql/postgres/migrations/.
        loader = (ROOT / "homologation" / "core-c1" / "run.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("/workspace/sql/postgres/[0-9][0-9][0-9]*.sql", loader)
        for path in (ROOT / "src").rglob("*.py"):
            self.assertNotIn("001_idx_magento_item_order_id", path.read_text(
                encoding="utf-8"
            ))


if __name__ == "__main__":
    unittest.main()

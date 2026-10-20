"""Guardas locais da preparação C1; não executa Docker nem PostgreSQL."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
C1 = ROOT / "homologation" / "core-c1"


def read(name: str) -> str:
    return (C1 / name).read_text(encoding="utf-8")


class CoreC1StaticTests(unittest.TestCase):
    def test_compose_is_local_and_version_pinned(self):
        compose = read("compose.yaml")
        self.assertIn("name: banco-central-core-c15", compose)
        self.assertIn("image: postgres:16.13-trixie", compose)
        self.assertIn("network_mode: none", compose)
        self.assertIn("profiles: [manual]", compose)
        self.assertNotRegex(compose, r"(?m)^\s*ports:")
        self.assertIn("../../sql:/workspace/sql:ro", compose)
        self.assertIn("./:/workspace/c1:ro", compose)
        self.assertIn("- core_c1_pgdata:/var/lib/postgresql/data", compose)
        self.assertNotIn("external:", compose)
        self.assertNotIn(".env", compose)

    def test_runner_rejects_nonlocal_destination(self):
        runner = read("run.sh")
        self.assertIn("PGHOST=/var/run/postgresql", runner)
        self.assertIn("PGDATABASE=core_c1_homolog", runner)
        self.assertIn("inet_server_addr() IS NULL", runner)
        self.assertIn("core_c1_homolog:core_c1:true:16*", runner)
        self.assertIn("assert_local\n", runner)
        self.assertIn("  assert_local\n  psql", runner)
        self.assertNotRegex(runner, r"\b(?:rm|rmdir|docker|drop|truncate)\b")
        for script in ("000_missing_sources.sql", "001_core_ddl.sql",
                       "002_core_helpers.sql"):
            self.assertIn(script, runner)

    def test_fixtures_are_synthetic_and_without_personal_values(self):
        fixtures = read("fixtures.sql")
        self.assertGreaterEqual(fixtures.count("'synthetic'"), 10)
        self.assertNotRegex(fixtures, r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
        self.assertNotRegex(fixtures, r"(?<!\d)\d{11}(?!\d)")
        self.assertNotRegex(fixtures, r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
        self.assertNotIn("raw.ativo_usuario", fixtures)
        self.assertNotIn("raw.magento_customer", fixtures)
        self.assertNotIn("COPY ", fixtures.upper())

    def test_test_plan_covers_required_cases(self):
        tests = read("tests.psql")
        for marker in (
            "003_core_upserts.sql", "005_core_inscricao_base_upsert.sql",
            "004_core_inscricao_candidates.sql", "900_core_acceptance_readonly.sql",
            "unique_violation", "check_violation", "flag_pedido_nao_encontrado",
            "comprador_id_origem IS NOT NULL", "staging.magento_bundle_componente",
            "discount_amount=12", "fato_inscricao_indicadores_validos",
            "100000", "100001", "C1_LOCAL_TESTS_PASSED",
        ):
            self.assertIn(marker, tests)
        self.assertEqual(tests.count("\\i /workspace/sql/core/proposed/003_core_upserts.sql"), 2)
        self.assertGreaterEqual(tests.count("\\i /workspace/sql/core/proposed/005_core_inscricao_base_upsert.sql"), 4)

    def test_c15_candidate_assertions_and_fresh_project(self):
        runner = read("run.sh")
        capture = read("capture_candidates.sh")
        fixtures = read("fixtures.sql")
        checks = read("tests.psql")
        candidates = (ROOT / "sql" / "core" / "proposed" / "004_core_inscricao_candidates.sql").read_text(encoding="utf-8")
        ddl = (ROOT / "sql" / "core" / "proposed" / "001_core_ddl.sql").read_text(encoding="utf-8")
        self.assertIn("tr -d '\\r' < /workspace/c1/capture_candidates.sh | sh", runner)
        self.assertIn("assert_fresh_schema", runner)
        self.assertIn("004_core_inscricao_candidates.sql", capture)
        self.assertIn("CREATE TEMP TABLE c1_magento_candidate AS", capture)
        self.assertIn("CREATE TEMP TABLE c1_ativo_candidate AS", capture)
        magento_sql = candidates.split("WITH pais AS MATERIALIZED (", 1)[1].split(
            "-- PENDÊNCIAS Magento antes do UPSERT:", 1)[0]
        ativo_sql = candidates.split("SELECT i.pedido_id, i.inscricao_id, fp.pedido_key,", 1)[1].split(
            "WHERE i.pedido_id BETWEEN core.batch_min() AND core.batch_max();", 1)[0]
        self.assertEqual(magento_sql.count(";"), 1)
        self.assertEqual(ativo_sql.count(";"), 0)
        self.assertIn("FROM staging.magento_inscricao", magento_sql)
        self.assertIn("FROM staging.ativo_inscricao", ativo_sql)
        for case_id in (3010, 3020, 3030, 3040, 3050, 3060):
            self.assertIn(f"({case_id},", fixtures)
        for case_id in (4101, 4201, 4301, 4401, 4501, 4601):
            self.assertIn(f"({case_id},", checks)
        for case_id in (5001, 5002, 5003, 5004):
            self.assertIn(f"({case_id},", checks)
        self.assertIn("IS DISTINCT FROM", checks)
        self.assertIn("taxa_servico_ativo", checks)
        self.assertIn("c1_aceite_historico_cobertura", checks)
        self.assertIn("C1_HISTORICAL_ACCEPTANCE_NOT_COVERED", checks)
        self.assertIn("POSITION('false' IN LOWER(pg_get_viewdef(", checks)
        self.assertIn("WHERE FALSE", ddl)
        self.assertNotIn("(166688,", fixtures)

    def test_no_production_address_or_credentials_in_artifacts(self):
        for path in C1.iterdir():
            if path.is_file():
                body = path.read_text(encoding="utf-8")
                self.assertNotRegex(body, r"\b(?:\d{1,3}\.){3}\d{1,3}\b", path.name)
                self.assertNotRegex(body, r"(?im)^\s*(?:senha|password|token)\s*[:=]", path.name)

    def test_discard_recipe_is_project_scoped(self):
        guide = read("README.md")
        self.assertIn("down --volumes", guide)
        self.assertIn("config --volumes", guide)
        self.assertNotIn("--remove-orphans", guide)
        self.assertNotIn("docker volume prune\n", guide)


if __name__ == "__main__":
    unittest.main()

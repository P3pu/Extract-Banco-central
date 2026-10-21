"""D4: sondas isoladas e janela mensal; nenhuma conexão de produção."""

import calendar
from datetime import date, timedelta
from pathlib import Path
import os
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest import TestCase, mock

from deploy.d1 import entrypoint


ROOT = Path(__file__).resolve().parents[1]
D1 = ROOT / "deploy" / "d1"


class D4Tests(TestCase):
    def test_each_probe_needs_only_its_own_settings_secret_and_ca(self):
        scenarios = {
            "postgres": ("POSTGRES_", "postgres_password", "postgres_ca.pem"),
            "magento": ("MAGENTO_MYSQL_", "magento_mysql_password", "mysql_ca.pem"),
            "ativo": ("ATIVO_MYSQL_", "ativo_mysql_password", "mysql_ca.pem"),
        }
        for source, (prefix, secret_name, ca_name) in scenarios.items():
            with self.subTest(source=source), TemporaryDirectory(dir=ROOT) as directory:
                secret_dir = Path(directory)
                (secret_dir / ca_name).write_text("synthetic-ca", encoding="ascii")
                (secret_dir / secret_name).write_text("synthetic-password", encoding="ascii")
                env = {prefix + "HOST": "db.example.invalid", prefix + "PORT": "3306",
                       prefix + "USER": "synthetic_user"}
                if source == "postgres":
                    env.update(POSTGRES_PORT="5432", POSTGRES_SSLMODE="verify-full",
                               PGSSLROOTCERT=str(secret_dir / ca_name))
                else:
                    env.update({prefix + "DATABASE": "synthetic_db",
                                "MYSQL_SSL_CA": str(secret_dir / ca_name)})
                fake_main = ModuleType("src.main")
                fake_main.main = mock.Mock(return_value=0)
                with mock.patch.object(entrypoint, "SECRET_DIR", secret_dir), \
                     mock.patch.dict(os.environ, env, clear=True), \
                     mock.patch.dict(sys.modules, {"src.main": fake_main}):
                    self.assertEqual(entrypoint.probe(source), 0)
                    fake_main.main.assert_called_once_with(["check", "--source", source])
                    own_password = entrypoint.SECRET_FILES[source][0]
                    self.assertEqual(os.environ[own_password], "synthetic-password")
                    for other in scenarios.keys() - {source}:
                        self.assertNotIn(entrypoint.SECRET_FILES[other][0], os.environ)

    def test_probe_rejects_missing_ca_bad_port_and_non_dns_host(self):
        with TemporaryDirectory(dir=ROOT) as directory:
            secret_dir = Path(directory)
            base = {"POSTGRES_HOST": "db.example.invalid", "POSTGRES_PORT": "5432",
                    "POSTGRES_USER": "synthetic_user", "POSTGRES_SSLMODE": "verify-full",
                    "PGSSLROOTCERT": str(secret_dir / "postgres_ca.pem")}
            with mock.patch.object(entrypoint, "SECRET_DIR", secret_dir):
                with mock.patch.dict(os.environ, base, clear=True):
                    with self.assertRaisesRegex(ValueError, "CA"):
                        entrypoint.validate_connection("postgres")
                (secret_dir / "postgres_ca.pem").write_text("synthetic-ca", encoding="ascii")
                for overrides, expected in (({"POSTGRES_PORT": "0"}, "Porta"),
                                            ({"POSTGRES_HOST": "127.0.0.1"}, "Hostname"),
                                            ({"POSTGRES_SSLMODE": "require"}, "TLS")):
                    with self.subTest(overrides=overrides), mock.patch.dict(
                        os.environ, {**base, **overrides}, clear=True
                    ):
                        with self.assertRaisesRegex(ValueError, expected):
                            entrypoint.validate_connection("postgres")
                mysql_env = {"MAGENTO_MYSQL_HOST": "mysql.example.invalid",
                             "MAGENTO_MYSQL_PORT": "3306", "MAGENTO_MYSQL_USER": "synthetic",
                             "MAGENTO_MYSQL_DATABASE": "synthetic",
                             "MYSQL_SSL_CA": str(secret_dir / "mysql_ca.pem")}
                with mock.patch.dict(os.environ, mysql_env, clear=True):
                    with self.assertRaisesRegex(ValueError, "CA"):
                        entrypoint.validate_connection("magento")

    def test_loads_still_require_postgres_and_only_the_selected_mysql(self):
        with TemporaryDirectory(dir=ROOT) as directory:
            secret_dir = Path(directory)
            for filename in ("postgres_ca.pem", "mysql_ca.pem",
                             "postgres_password", "magento_mysql_password"):
                (secret_dir / filename).write_text("synthetic", encoding="ascii")
            common = {"POSTGRES_HOST": "pg.example.invalid", "POSTGRES_PORT": "5432",
                      "POSTGRES_USER": "synthetic", "POSTGRES_SSLMODE": "verify-full",
                      "PGSSLROOTCERT": str(secret_dir / "postgres_ca.pem"),
                      "MYSQL_SSL_CA": str(secret_dir / "mysql_ca.pem")}
            magento = {"MAGENTO_MYSQL_HOST": "magento.example.invalid",
                       "MAGENTO_MYSQL_PORT": "3306", "MAGENTO_MYSQL_USER": "synthetic",
                       "MAGENTO_MYSQL_DATABASE": "synthetic"}
            ativo = {"ATIVO_MYSQL_HOST": "ativo.example.invalid",
                     "ATIVO_MYSQL_PORT": "3306", "ATIVO_MYSQL_USER": "synthetic",
                     "ATIVO_MYSQL_DATABASE": "synthetic"}
            fake_main = ModuleType("src.main")
            fake_main.main = mock.Mock(return_value=0)
            with mock.patch.object(entrypoint, "SECRET_DIR", secret_dir), \
                 mock.patch.dict(sys.modules, {"src.main": fake_main}):
                with mock.patch.dict(os.environ, {**magento, "D1_ENABLE_INCREMENTALS": "approved"}, clear=True):
                    with self.assertRaisesRegex(ValueError, "Destino"):
                        entrypoint.incremental("magento", "sales_order")
                with mock.patch.dict(os.environ, {**common, "D1_ENABLE_INCREMENTALS": "approved"}, clear=True):
                    with self.assertRaisesRegex(ValueError, "Destino"):
                        entrypoint.incremental("magento", "sales_order")
                with mock.patch.dict(os.environ, {**common, **magento,
                                                  "D1_ENABLE_INCREMENTALS": "approved"}, clear=True):
                    self.assertEqual(entrypoint.incremental("magento", "sales_order"), 0)
                fake_main.main.assert_called_once_with(["incremental", "--source", "magento",
                                                        "--entity", "sales_order"])
                fake_main.main.reset_mock()
                (secret_dir / "magento_mysql_password").unlink()
                (secret_dir / "ativo_mysql_password").write_text("synthetic", encoding="ascii")
                with mock.patch.dict(os.environ, {**ativo,
                                                  "D1_ENABLE_RECONCILIATION": "approved",
                                                  "RECONCILIATION_DAYS": "35"}, clear=True):
                    with self.assertRaisesRegex(ValueError, "Destino"):
                        entrypoint.reconcile("pedido")
                with mock.patch.dict(os.environ, {**common, **ativo,
                                                  "D1_ENABLE_RECONCILIATION": "approved",
                                                  "RECONCILIATION_DAYS": "35"}, clear=True):
                    self.assertEqual(entrypoint.reconcile("pedido"), 0)
                fake_main.main.assert_called_once_with(["reconcile", "--source", "ativo",
                                                        "--entity", "pedido", "--days", "35"])

    def test_monthly_35_day_window_covers_all_month_lengths_with_overlap(self):
        for year in range(2024, 2030):
            for month in range(1, 13):
                start = date(year, month, 1)
                end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
                gap = (end - start).days
                with self.subTest(year=year, month=month):
                    self.assertEqual(gap, calendar.monthrange(year, month)[1])
                    self.assertIn(gap, (28, 29, 30, 31))
                    self.assertGreaterEqual((start + timedelta(days=35) - end).days, 4)
        self.assertIn("OnCalendar=*-*-01 03:00:00",
                      (D1 / "systemd" / "bcd-d1-reconciliation.timer").read_text(encoding="utf-8"))
        self.assertIn("RECONCILIATION_DAYS=35", (D1 / ".env.example").read_text(encoding="utf-8"))
        self.assertIn("RECONCILIATION_DAYS: ${RECONCILIATION_DAYS:-35}",
                      (D1 / "compose.yaml").read_text(encoding="utf-8"))

    def test_reconcile_refuses_shorter_or_unbounded_window_before_connections(self):
        for days in ("0", "30", "31", "34", "36", "365", "UNSET"):
            with self.subTest(days=days), mock.patch.dict(
                os.environ, {"D1_ENABLE_RECONCILIATION": "approved",
                             "RECONCILIATION_DAYS": days}, clear=True
            ), mock.patch.object(entrypoint, "validate_connection") as validate:
                with self.assertRaisesRegex(ValueError, "35 dias"):
                    entrypoint.reconcile("pedido")
                validate.assert_not_called()
        incremental = (D1 / "run_incrementals.sh").read_text(encoding="utf-8")
        reconciliation = (D1 / "run_reconciliation.sh").read_text(encoding="utf-8")
        self.assertIn('"$lock_dir/global.lock"', incremental)
        self.assertIn('"$lock_dir/global.lock"', reconciliation)
        self.assertIn("flock -n 9", reconciliation)

    def test_release_identity_and_security_checklist_are_versioned(self):
        compose = (D1 / "compose.yaml").read_text(encoding="utf-8")
        doc = (ROOT / "docs" / "DEPLOY_D4_NARUTO_PREPARACAO.md").read_text(encoding="utf-8")
        self.assertIn("banco-central-executor:${D1_COMMIT_SHA:-unreleased}", compose)
        self.assertIn("org.opencontainers.image.revision", compose)
        self.assertIn("D1_COMMIT_SHA=unreleased", (D1 / ".env.example").read_text(encoding="utf-8"))
        for marker in ("git archive", "sha256sum -c", "UID/GID `10001`",
                       "rollback", "docker.sock", "verify-full", "18 testes"):
            self.assertIn(marker, doc)
        self.assertNotRegex(doc, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        self.assertNotRegex(doc, r"SHA256:[A-Za-z0-9+/]{43}")

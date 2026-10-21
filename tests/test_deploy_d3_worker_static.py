"""Guardas do Compose no worker: somente arquivos e mocks, sem produção."""

from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
from types import ModuleType
from unittest import TestCase, mock

from deploy.d1 import entrypoint


ROOT = Path(__file__).resolve().parents[1]
D1 = ROOT / "deploy" / "d1"


class WorkerComposeTests(TestCase):
    def test_isolation_and_limits(self):
        compose = (D1 / "compose.yaml").read_text(encoding="utf-8")
        operative = "\n".join(line for line in compose.splitlines()
                              if not line.lstrip().startswith("#"))
        for marker in ('driver: bridge', 'cpus: "0.50"', 'mem_limit: 768m',
                       'mem_reservation: 256m', 'pids_limit: 128',
                       'D1_ENABLE_INCREMENTALS: ${D1_ENABLE_INCREMENTALS:-no}',
                       'D1_ENABLE_RECONCILIATION: ${D1_ENABLE_RECONCILIATION:-no}',
                       'POSTGRES_SSLMODE: ${POSTGRES_SSLMODE:-verify-full}'):
            self.assertIn(marker, operative)
        for forbidden in ('network_swarm_public', 'overlay', 'docker.sock',
                          'pgdata', 'ports:', 'privileged: true'):
            self.assertNotIn(forbidden, operative)

    def test_probe_is_readonly_cli_and_reconcile_is_gated(self):
        fake_main = ModuleType("src.main")
        fake_main.main = mock.Mock(return_value=0)
        with mock.patch.dict("os.environ", {"D1_ENABLE_RECONCILIATION": "no"}):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(entrypoint.main(["reconcile", "--entity", "pedido"]), 1)
        with mock.patch.object(entrypoint, "validate_connection"), \
             mock.patch.object(entrypoint, "load_secrets"), \
             mock.patch.dict(sys.modules, {"src.main": fake_main}):
            self.assertEqual(entrypoint.probe("postgres"), 0)
            fake_main.main.assert_called_once_with(["check", "--source", "postgres"])
        fake_main.main.reset_mock()
        with mock.patch.dict("os.environ", {"D1_ENABLE_RECONCILIATION": "approved"}), \
             mock.patch.object(entrypoint, "validate_connection"), \
             mock.patch.object(entrypoint, "load_secrets"), \
             mock.patch.dict(sys.modules, {"src.main": fake_main}):
            self.assertEqual(entrypoint.reconcile("pedido"), 0)
            fake_main.main.assert_called_once_with(["reconcile", "--source", "ativo", "--entity", "pedido"])

    def test_same_host_lock_and_root_owned_units(self):
        incremental = (D1 / "run_incrementals.sh").read_text(encoding="utf-8")
        reconciliation = (D1 / "run_reconciliation.sh").read_text(encoding="utf-8")
        for runner in (incremental, reconciliation):
            self.assertIn('"$lock_dir/global.lock"', runner)
            self.assertIn("flock -n 9", runner)
            self.assertIn("exit 75", runner)
            self.assertNotIn("docker compose up", runner)
        self.assertIn("reconcile --entity", reconciliation)
        for name in ("magento", "ativo", "reconciliation"):
            unit = (D1 / "systemd" / f"bcd-d1-{name}.service").read_text(encoding="utf-8")
            self.assertIn("User=root", unit)
            self.assertIn("ProtectSystem=strict", unit)
            self.assertNotIn("User=bcdsvc", unit)
            timer = (D1 / "systemd" / f"bcd-d1-{name}.timer").read_text(encoding="utf-8")
            self.assertIn("Persistent=false", timer)

    def test_no_real_endpoints_or_credentials_in_new_doc(self):
        doc = (ROOT / "docs" / "DEPLOY_D3_WORKER_COMPOSE.md").read_text(encoding="utf-8")
        self.assertNotRegex(doc, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        self.assertNotRegex(doc, r"SHA256:[A-Za-z0-9+/]{43}")
        self.assertNotIn("D1_ENABLE_INCREMENTALS=approved", doc)

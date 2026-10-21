"""D1: guardas locais de arquivos, sem SSH, Docker up ou banco."""

from pathlib import Path
from unittest import mock
from contextlib import redirect_stderr
import io
import unittest

from deploy.d1 import entrypoint


ROOT = Path(__file__).resolve().parents[1]
D1 = ROOT / "deploy" / "d1"


class DeployD1StaticTests(unittest.TestCase):
    def test_gate_defaults_closed_and_no_full_route(self):
        compose = (D1 / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("D1_ENABLE_INCREMENTALS: ${D1_ENABLE_INCREMENTALS:-no}", compose)
        with redirect_stderr(io.StringIO()):
            with mock.patch.dict("os.environ", {"D1_ENABLE_INCREMENTALS": "no"}):
                self.assertEqual(entrypoint.main([
                    "incremental", "--source", "magento", "--entity", "sales_order"
                ]), 1)
            with mock.patch.dict("os.environ", {"D1_ENABLE_INCREMENTALS": "approved"}):
                self.assertEqual(entrypoint.main([
                    "incremental", "--source", "magento", "--entity", "customer"
                ]), 1)
        self.assertEqual(entrypoint.ALLOWED, {
            "magento": frozenset({"sales_order", "sales_order_item"}),
            "ativo": frozenset({"pedido", "pedido_evento"}),
        })
        self.assertNotIn('commands.add_parser("full")',
                         (D1 / "entrypoint.py").read_text(encoding="utf-8"))

    def test_compose_is_separate_and_no_db_volume_or_ports(self):
        compose = (D1 / "compose.yaml").read_text(encoding="utf-8")
        for expected in (
            "name: banco-central-executor-d1", "profiles: [manual]",
            'user: "10001:10001"', "read_only: true",
            "cap_drop: [ALL]", "no-new-privileges:true",
            "restart: unless-stopped", "/run/d1-secrets:ro",
            "deploy.d1.entrypoint", "source_egress",
        ):
            self.assertIn(expected, compose)
        self.assertNotRegex(compose, r"(?m)^\s*ports\s*:")
        operative = "\n".join(line for line in compose.splitlines()
                              if not line.lstrip().startswith("#"))
        self.assertNotRegex(operative, r"(?i)pgdata|core_c1_pgdata|raw_r1_pgdata")
        self.assertNotRegex(compose, r"(?i)postgres_password\s*:")

    def test_host_runner_serializes_and_uses_explicit_incremental(self):
        runner = (D1 / "run_incrementals.sh").read_text(encoding="utf-8")
        body = "\n".join(line for line in runner.splitlines()
                         if not line.lstrip().startswith("#"))
        self.assertIn("flock -n 9", body)
        self.assertIn("exit 75", body)
        self.assertIn("exec -T executor python -m deploy.d1.entrypoint", body)
        self.assertIn('incremental --source "$1" --entity "$entity"', body)
        self.assertNotRegex(body, r"(?i)\b(?:full|reconcile|snapshot|init)\b")
        self.assertIn("sales_order sales_order_item", body)
        self.assertIn("pedido pedido_evento", body)

    def test_secrets_are_files_not_command_arguments_or_image(self):
        dockerfile = (D1 / "Dockerfile").read_text(encoding="utf-8")
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        example = (D1 / ".env.example").read_text(encoding="utf-8")
        entry = (D1 / "entrypoint.py").read_text(encoding="utf-8")
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn("**/.env*", ignore)
        self.assertIn("**/secrets/", ignore)
        self.assertIn("**/certs/", ignore)
        self.assertIn("/run/d1-secrets", entry)
        self.assertIn("load_secrets()", entry)
        self.assertNotRegex(example, r"(?m)^[A-Z_]*PASSWORD=")
        self.assertNotRegex(dockerfile, r"(?i)\b(?:ARG|ENV)\s+.*password")

    def test_pins_and_systemd_not_activated(self):
        lock = (D1 / "requirements.lock").read_text(encoding="utf-8")
        for line in lock.splitlines():
            if line and not line.startswith("#"):
                self.assertRegex(line, r"^[A-Za-z0-9_\-\[\]]+==\d+\.\d+\.\d+$")
        for name in ("magento", "ativo"):
            service = (D1 / "systemd" / f"bcd-d1-{name}.service").read_text(
                encoding="utf-8"
            )
            timer = (D1 / "systemd" / f"bcd-d1-{name}.timer").read_text(
                encoding="utf-8"
            )
            self.assertIn("Type=oneshot", service)
            self.assertIn("User=bcdsvc", service)
            self.assertIn("StateDirectory=bcd-d1", service)
            self.assertIn(f"run_incrementals.sh {name}", service)
            self.assertIn("Persistent=false", timer)
            self.assertNotIn("ExecStart=systemctl", service)

    def test_documentation_flags_unverified_host_and_backlog(self):
        doc = (ROOT / "docs" / "DEPLOY_D1_NARUTO.md").read_text(
            encoding="utf-8"
        )
        for marker in ("NÃO VERIFICADOS", "28/09/2026", "flock",
                       "não há ainda canal externo", "não instalados",
                       "sem `down --volumes`", "FULL"):
            self.assertIn(marker, doc)
        self.assertNotRegex(doc, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        self.assertNotRegex(doc, r"SHA256:[A-Za-z0-9+/]{43}")


if __name__ == "__main__":
    unittest.main()

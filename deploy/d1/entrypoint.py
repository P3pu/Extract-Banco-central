"""Executor D1: sem FULL, desabilitado por padrão e sem segredos em argumentos."""

import argparse
import os
from pathlib import Path
import signal
import sys
import time


HEARTBEAT = Path("/tmp/bcd-d1-heartbeat")
SECRET_DIR = Path("/run/d1-secrets")
SECRET_FILES = {
    "POSTGRES_PASSWORD": "postgres_password",
    "MAGENTO_MYSQL_PASSWORD": "magento_mysql_password",
    "ATIVO_MYSQL_PASSWORD": "ativo_mysql_password",
}
ALLOWED = {
    "magento": frozenset({"sales_order", "sales_order_item"}),
    "ativo": frozenset({"pedido", "pedido_evento"}),
}


def serve() -> int:
    """Mantém container ocioso/observável; nunca agenda ou executa cargas."""
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        HEARTBEAT.write_text(str(time.time()), encoding="ascii")
        time.sleep(10)
    HEARTBEAT.unlink(missing_ok=True)
    return 0


def health() -> int:
    """Sinaliza liveness do executor, não sucesso ou conectividade da ETL."""
    try:
        age = time.time() - float(HEARTBEAT.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return 1
    return 0 if 0 <= age <= 60 else 1


def load_secrets() -> None:
    for env_name, filename in SECRET_FILES.items():
        path = SECRET_DIR / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError("Arquivo de segredo obrigatório ausente ou inválido")
        value = path.read_text(encoding="utf-8")
        if value.endswith("\n"):
            value = value[:-1]
        if not value or "\n" in value or "\r" in value:
            raise ValueError("Formato de segredo inválido")
        os.environ[env_name] = value


def incremental(source: str, entity: str) -> int:
    if os.environ.get("D1_ENABLE_INCREMENTALS") != "approved":
        raise ValueError("Incrementais D1 desabilitados")
    if entity not in ALLOWED.get(source, ()):
        raise ValueError("Entidade fora da primeira onda D1 aprovada")
    required = ("POSTGRES_HOST", "POSTGRES_USER", "MAGENTO_MYSQL_HOST",
                "MAGENTO_MYSQL_DATABASE", "MAGENTO_MYSQL_USER",
                "ATIVO_MYSQL_HOST", "ATIVO_MYSQL_DATABASE", "ATIVO_MYSQL_USER")
    if any(os.environ.get(key, "UNSET") in {"", "UNSET"} for key in required):
        raise ValueError("Destino ou usuário não configurado")
    for name in ("postgres_ca.pem", "mysql_ca.pem"):
        if not (SECRET_DIR / name).is_file():
            raise ValueError("CA de TLS ausente")
    load_secrets()
    from src.main import main
    return main(["incremental", "--source", source, "--entity", entity])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Executor D1 sem carga FULL")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve")
    commands.add_parser("health")
    inc = commands.add_parser("incremental")
    inc.add_argument("--source", choices=sorted(ALLOWED), required=True)
    inc.add_argument("--entity", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            return serve()
        if args.command == "health":
            return health()
        return incremental(args.source, args.entity)
    except (OSError, ValueError) as exc:
        # Nunca imprimir caminho, valor do segredo ou mensagem de driver.
        print(f"ERROR: {type(exc).__name__} no controle D1", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

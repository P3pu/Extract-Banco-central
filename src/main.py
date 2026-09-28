"""CLI RAW: infraestrutura e sales_order (Fases 1 e 2)."""

import argparse
import json
from pathlib import Path

from src.config.settings import ConfigurationError, Settings


def safe_error(exc):
    """Classifica a falha sem expor a mensagem original do driver."""
    detail = str(exc).lower()
    categories = [
        (("certificate_verify_failed", "certificate verify failed"), "certificado TLS não confiável ou hostname inválido"),
        (("does not support ssl", "ssl is required but the server"), "servidor não oferece TLS"),
        (("access denied", "password authentication failed"), "autenticação recusada"),
        (("unknown database", "database does not exist"), "database indisponível"),
        (("getaddrinfo", "name or service not known", "could not translate host"), "nome do servidor não resolvido"),
        (("timed out", "timeout expired"), "tempo de conexão esgotado"),
        (("connection refused", "actively refused", "10061"), "conexão recusada pelo servidor"),
    ]
    for patterns, description in categories:
        if any(pattern in detail for pattern in patterns):
            return description
    return f"falha de conexão/operação ({type(exc).__name__})"


def parser():
    root = argparse.ArgumentParser(description="Pipeline RAW — Fases 1 e 2")
    root.add_argument("--env-file", type=Path)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Cria raw e tabelas técnicas no Atendimento")
    check = commands.add_parser("check", help="Verifica conexões sem alterar tabelas")
    check.add_argument("--source", choices=["magento", "ativo", "postgres"])
    inspect = commands.add_parser("inspect", help="Consulta somente metadados MySQL")
    inspect.add_argument("--source", choices=["magento", "ativo"], required=True)
    inspect.add_argument("--table", required=True)
    for mode in ("full", "incremental"):
        load = commands.add_parser(mode, help="Carga de Magento sales_order")
        load.add_argument("--source", choices=["magento"], default="magento")
        load.add_argument("--entity", choices=["sales_order"], default="sales_order")
        load.add_argument("--batch-size", type=int)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        settings = Settings.load(**({"env_file": args.env_file} if args.env_file else {}))
        if args.command in {"full", "incremental"}:
            from src.pipeline.sales_order import run
            run(settings, args.command.upper(), args.batch_size)
        elif args.command == "init":
            from src.db.postgres import connect, initialize
            with connect(settings) as connection:
                initialize(connection)
            print("SUCCESS: schema raw e tabelas técnicas disponíveis em Atendimento")
        elif args.command == "check":
            for source in ([args.source] if args.source else ["postgres", "magento", "ativo"]):
                if source == "postgres":
                    from src.db.postgres import connect
                    with connect(settings):
                        pass
                else:
                    from src.db.mysql import connect
                    with connect(settings, source) as reader:
                        if reader.ping() != settings.database(source).database:
                            raise RuntimeError("Database inesperado")
                print(f"SUCCESS: conexão {source}")
        else:
            from src.db.mysql import connect
            database = settings.database(args.source).database
            with connect(settings, args.source) as reader:
                columns = reader.columns(database, args.table)
                if not columns:
                    raise ConfigurationError("Tabela ausente ou metadados sem permissão")
                print(json.dumps({"columns": columns, "indexes": reader.indexes(database, args.table)},
                                 default=str, ensure_ascii=False, indent=2))
        return 0
    except ConfigurationError as exc:
        print(f"ERROR: {exc}")
    except Exception as exc:
        # Mensagens de drivers podem conter SQL, dados pessoais ou parâmetros.
        print(f"ERROR: {safe_error(exc)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

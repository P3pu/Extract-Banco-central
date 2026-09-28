"""CLI RAW: Magento e Ativo, incluindo snapshots referenciais (Fase 6)."""

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
    root = argparse.ArgumentParser(description="Pipeline RAW — Fases 1 a 6")
    root.add_argument("--env-file", type=Path)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Cria raw e tabelas técnicas no Atendimento")
    check = commands.add_parser("check", help="Verifica conexões sem alterar tabelas")
    check.add_argument("--source", choices=["magento", "ativo", "postgres"])
    inspect = commands.add_parser("inspect", help="Consulta somente metadados MySQL")
    inspect.add_argument("--source", choices=["magento", "ativo"], required=True)
    inspect.add_argument("--table", required=True)
    for mode in ("full", "incremental"):
        load = commands.add_parser(mode, help="Carga de Magento e Ativo")
        load.add_argument("--source", choices=["magento", "ativo"])
        load.add_argument("--entity", choices=["sales_order", "sales_order_item", "pedido", "pedido_evento"])
        load.add_argument("--batch-size", type=int)
    reconcile = commands.add_parser("reconcile", help="Reconcilia pedidos e inscrições Ativo")
    reconcile.add_argument("--source", choices=["ativo"], default="ativo")
    reconcile.add_argument("--entity", choices=["pedido", "pedido_evento"])
    reconcile.add_argument("--batch-size", type=int)
    reconcile.add_argument("--days", type=int)
    snapshot = commands.add_parser("snapshot", help="Sincroniza referências Ativo de forma transacional")
    snapshot.add_argument("--source", choices=["ativo"], default="ativo")
    snapshot.add_argument("--entity", choices=["evento"], default="evento")
    snapshot.add_argument("--batch-size", type=int)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        settings = Settings.load(**({"env_file": args.env_file} if args.env_file else {}))
        if args.command in {"full", "incremental", "reconcile", "snapshot"}:
            if args.command == "snapshot":
                from src.pipeline.ativo_snapshot import run
                run(settings, args.batch_size, entity=args.entity)
            elif args.command == "reconcile":
                from src.pipeline.ativo_pedido import run
                for entity in ([args.entity] if args.entity else ["pedido", "pedido_evento"]):
                    run(settings, "RECONCILIATION", args.batch_size, args.days, entity=entity)
            else:
                source = args.source or ("ativo" if args.entity in ("pedido", "pedido_evento") else "magento" if args.entity else None)
                if source == "ativo" and args.entity not in (None, "pedido", "pedido_evento"):
                    raise ConfigurationError("Entidade incompatível com Ativo")
                if source == "magento" and args.entity in ("pedido", "pedido_evento"):
                    raise ConfigurationError("Entidade incompatível com Magento")
                if source != "ativo":
                    from src.pipeline.sales_order import run
                    for entity in ([args.entity] if args.entity else ["sales_order", "sales_order_item"]):
                        run(settings, args.command.upper(), args.batch_size, entity=entity)
                if source != "magento":
                    from src.pipeline.ativo_pedido import run
                    for entity in ([args.entity] if args.entity else ["pedido", "pedido_evento"]):
                        run(settings, args.command.upper(), args.batch_size, entity=entity)
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

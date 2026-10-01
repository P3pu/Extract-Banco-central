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
        entities = ["sales_order", "sales_order_item", "product", "customer", "customer_address",
                    "customer_order_item", "product_varchar",
                    "product_int", "product_datetime",
                    "pedido", "pedido_evento",
                    "usuario", "usuario_balcao", "pedido_pagamento", "transacao",
                    "pedido_produto", "pedido_endereco"]
        if mode == "incremental":
            entities.append("cupom_desconto_item")
        load.add_argument("--entity", choices=entities)
        load.add_argument("--batch-size", type=int)
    reconcile = commands.add_parser("reconcile", help="Reconcilia entidades Ativo")
    reconcile.add_argument("--source", choices=["ativo"], default="ativo")
    reconcile.add_argument("--entity", choices=["pedido", "pedido_evento", "usuario", "usuario_balcao",
                                                "pedido_pagamento", "transacao", "pedido_endereco",
                                                "cupom_desconto_item"])
    reconcile.add_argument("--batch-size", type=int)
    reconcile.add_argument("--days", type=int)
    snapshot = commands.add_parser("snapshot", help="Sincroniza referenciais e EAV de forma transacional")
    snapshot.add_argument("--source", choices=["ativo", "magento"])
    snapshot.add_argument("--entity", choices=["evento", "evento_modalidade",
                                              "modalidade_categoria", "pedido_status",
                                              "tamanho_camiseta", "formas_pagamento",
                                              "produto", "combo", "cidade", "estado", "pais",
                                              "pedido_produto", "product_varchar", "product_int",
                                              "product_datetime", "eav_attribute", "option_value",
                                              "customer_order_item"])
    snapshot.add_argument("--batch-size", type=int)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        settings = Settings.load(**({"env_file": args.env_file} if args.env_file else {}))
        if args.command in {"full", "incremental", "reconcile", "snapshot"}:
            if args.command == "snapshot":
                source = args.source or ("magento" if args.entity in {"product_varchar", "product_int",
                                                                   "product_datetime", "eav_attribute",
                                                                   "option_value", "customer_order_item"}
                                         else "ativo")
                if source == "magento":
                    if args.entity not in (None, "product_varchar", "product_int",
                                           "product_datetime", "eav_attribute", "option_value",
                                           "customer_order_item"):
                        raise ConfigurationError("Entidade incompatível com Magento")
                    for entity in ([args.entity] if args.entity else ["product_varchar", "product_int",
                                                                  "product_datetime", "eav_attribute",
                                                                  "option_value"]):
                        if entity == "customer_order_item":
                            from src.pipeline.magento_customer_order_item import run
                        elif entity == "product_varchar":
                            from src.pipeline.magento_product_varchar import run
                        elif entity == "product_int":
                            from src.pipeline.magento_product_int import run
                        elif entity == "product_datetime":
                            from src.pipeline.magento_product_datetime import run
                        elif entity == "eav_attribute":
                            from src.pipeline.magento_eav_attribute import run
                        else:
                            from src.pipeline.magento_option_value import run
                        run(settings, "SNAPSHOT", args.batch_size)
                else:
                    if args.entity in {"product_varchar", "product_int", "product_datetime",
                                       "eav_attribute", "option_value", "customer_order_item"}:
                        raise ConfigurationError("Entidade incompatível com Ativo")
                    from src.pipeline.ativo_snapshot import ENTITIES, run as run_reference
                    for entity in ([args.entity] if args.entity else [*ENTITIES, "pedido_produto"]):
                        if entity == "pedido_produto":
                            from src.pipeline.ativo_complementos import run
                            run(settings, "SNAPSHOT", args.batch_size, entity=entity)
                        else:
                            run_reference(settings, args.batch_size, entity=entity)
            elif args.command == "reconcile":
                for entity in ([args.entity] if args.entity else ["pedido", "pedido_evento",
                                                                  "usuario", "usuario_balcao",
                                                                  "pedido_pagamento", "pedido_endereco"]):
                    if entity == "cupom_desconto_item":
                        if args.days is not None:
                            raise ConfigurationError("--days não se aplica à reconciliação por referências de cupons")
                        from src.pipeline.ativo_cupom import run
                        run(settings, "RECONCILIATION", args.batch_size)
                        continue
                    if entity in ("pedido", "pedido_evento"):
                        from src.pipeline.ativo_pedido import run
                    elif entity in ("usuario", "usuario_balcao"):
                        from src.pipeline.ativo_usuario import run
                    elif entity == "pedido_pagamento" or entity == "transacao":
                        from src.pipeline.ativo_financeiro import run
                    else:
                        from src.pipeline.ativo_complementos import run
                    run(settings, "RECONCILIATION", args.batch_size, args.days, entity=entity)
            else:
                ativo_entities = ("pedido", "pedido_evento", "usuario", "usuario_balcao",
                                  "pedido_pagamento", "transacao", "pedido_produto",
                                  "pedido_endereco") + (("cupom_desconto_item",)
                                                         if args.command == "incremental" else ())
                source = args.source or ("ativo" if args.entity in ativo_entities else "magento" if args.entity else None)
                if source == "ativo" and args.entity not in (None, *ativo_entities):
                    raise ConfigurationError("Entidade incompatível com Ativo")
                if source == "magento" and args.entity in ativo_entities:
                    raise ConfigurationError("Entidade incompatível com Magento")
                if source != "ativo":
                    from src.pipeline.sales_order import run
                    for entity in ([args.entity] if args.entity else ["sales_order", "sales_order_item",
                                                                  "product", "customer", "customer_address",
                                                                  "customer_order_item",
                                                                  "product_varchar", "product_int",
                                                                  "product_datetime"]):
                        if entity == "customer_order_item":
                            from src.pipeline.magento_customer_order_item import run as run_relation
                            run_relation(settings, args.command.upper(), args.batch_size)
                        elif entity == "product_varchar":
                            from src.pipeline.magento_product_varchar import run as run_varchar
                            run_varchar(settings, args.command.upper(), args.batch_size)
                        elif entity == "product_int":
                            from src.pipeline.magento_product_int import run as run_int
                            run_int(settings, args.command.upper(), args.batch_size)
                        elif entity == "product_datetime":
                            from src.pipeline.magento_product_datetime import run as run_datetime
                            run_datetime(settings, args.command.upper(), args.batch_size)
                        else:
                            run(settings, args.command.upper(), args.batch_size, entity=entity)
                if source != "magento":
                    for entity in ([args.entity] if args.entity else ativo_entities):
                        if entity == "cupom_desconto_item":
                            from src.pipeline.ativo_cupom import run
                            run(settings, args.command.upper(), args.batch_size)
                            continue
                        if entity in ("pedido", "pedido_evento"):
                            from src.pipeline.ativo_pedido import run
                        elif entity in ("usuario", "usuario_balcao"):
                            from src.pipeline.ativo_usuario import run
                        elif entity in ("pedido_pagamento", "transacao"):
                            from src.pipeline.ativo_financeiro import run
                        else:
                            from src.pipeline.ativo_complementos import run
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

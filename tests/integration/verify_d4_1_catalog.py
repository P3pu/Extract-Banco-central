"""Opt-in: somente PostgreSQL local efêmero sem rede; nunca usar no Naruto."""

import os
from pathlib import Path

import psycopg

from src.loaders.postgres_loader import validate_target
from src.sources.ativo import pedido, pedido_evento
from src.sources.magento import sales_order, sales_order_item


if __name__ == "__main__":
    if os.environ.get("D4_1_SYNTHETIC_ONLY") != "yes":
        raise SystemExit("D4_1_SYNTHETIC_ONLY=yes obrigatório")
    root = (Path(os.environ["D4_1_REPO_ROOT"]) if "D4_1_REPO_ROOT" in os.environ
            else Path(__file__).resolve().parents[2])
    contracts = (
        ("003_create_magento_raw.sql", ("raw", "magento_sales_order"), sales_order),
        ("003b_create_magento_sales_order_item.sql", ("raw", "magento_sales_order_item"), sales_order_item),
        ("004_create_ativo_raw.sql", ("raw", "ativo_pedido"), pedido),
        ("005_create_ativo_pedido_evento_raw.sql", ("raw", "ativo_pedido_evento"), pedido_evento),
    )
    with psycopg.connect(host="127.0.0.1", port=5432, dbname="postgres", user="postgres",
                         sslmode="disable") as connection:
        connection.execute("CREATE SCHEMA raw")
        for filename, target, contract in contracts:
            connection.execute((root / "sql/postgres" / filename).read_text(encoding="utf-8"))
            validate_target(connection, target, contract)
        try:
            validate_target(connection, ("raw", "missing_synthetic_table"), sales_order)
        except ValueError:
            pass
        else:
            raise AssertionError("Tabela ausente aceita")
        connection.execute("ALTER TABLE raw.ativo_pedido_evento ALTER COLUMN fl_amigo TYPE CHAR(1)")
        try:
            validate_target(connection, ("raw", "ativo_pedido_evento"), pedido_evento)
        except ValueError:
            pass
        else:
            raise AssertionError("Tipo incompatível aceito")
    print("D4_1_LOCAL_CATALOG_PASSED")

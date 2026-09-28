from contextlib import contextmanager

import psycopg

from src.config.settings import ROOT


@contextmanager
def connect(settings):
    config = settings.database("postgres")
    with psycopg.connect(
        host=config.host, port=config.port, dbname=config.database,
        user=config.user, password=config.password, sslmode=settings.sslmode,
        connect_timeout=settings.connect_timeout,
        application_name="extract-banco-central",
        options="-c timezone=UTC -c lock_timeout=10000 -c statement_timeout=60000",
    ) as connection:
        actual = connection.execute("SELECT current_database()").fetchone()[0]
        if actual != "Atendimento":
            raise RuntimeError("Conexão recusada: database inesperado")
        yield connection


def initialize(connection):
    # Todos os DDLs pertencem à mesma transação. Exceções desfazem o conjunto.
    for filename in ("001_create_raw_schema.sql", "002_create_control_tables.sql"):
        connection.execute((ROOT / "sql" / "postgres" / filename).read_text(encoding="utf-8"))

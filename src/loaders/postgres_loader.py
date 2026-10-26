from datetime import datetime, timezone
import re

from psycopg import sql
from src.sources.magento.sales_order import COLUMNS


METADATA_FIELDS = {
    "_source": ("TEXT", False),
    "_extracted_at": ("TIMESTAMPTZ", False),
    "_batch_id": ("UUID", False),
}


def _pg_type(sql_type):
    simple = {"BIGINT": "int8", "INTEGER": "int4", "TEXT": "text",
              "TIMESTAMP": "timestamp", "TIMESTAMPTZ": "timestamptz", "UUID": "uuid"}
    if sql_type in simple:
        return simple[sql_type], -1
    sized = re.fullmatch(r"(VARCHAR|CHAR)\((\d+)\)", sql_type)
    if sized:
        return ("varchar" if sized[1] == "VARCHAR" else "bpchar", int(sized[2]) + 4)
    numeric = re.fullmatch(r"NUMERIC\((\d+),(\d+)\)", sql_type)
    if numeric:
        precision, scale = int(numeric[1]), int(numeric[2])
        return "numeric", ((precision << 16) | scale) + 4
    raise ValueError("Tipo RAW não suportado pelo verificador")


def validate_target(connection, target, contract):
    """Confere o contrato RAW versionado via catálogo, sem DDL ou dados de negócio."""
    schema, table = target
    rows = connection.execute(
        "SELECT c.relkind,c.relpersistence,a.attname,t.typname,a.atttypmod,"
        "a.attnotnull,a.attgenerated,a.attidentity "
        "FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid "
        "JOIN pg_catalog.pg_type t ON t.oid=a.atttypid "
        "WHERE n.nspname=%s AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped "
        "ORDER BY a.attnum", (schema, table)).fetchall()
    if not rows:
        raise ValueError(f"Tabela RAW ausente: {schema}.{table}")
    expected = {name: (sql_type, nullable)
                for name, (_, sql_type, nullable) in contract.FIELDS.items()}
    expected.update(METADATA_FIELDS)
    actual = {row[2]: row for row in rows}
    if set(actual) != set(expected):
        raise ValueError(f"Colunas RAW divergentes: {schema}.{table}")
    if any(row[0] != "r" or row[1] != "p" for row in rows):
        raise ValueError(f"Destino RAW não é tabela permanente: {schema}.{table}")
    for name, (sql_type, nullable) in expected.items():
        row = actual[name]
        if ((row[3], row[4]) != _pg_type(sql_type) or row[5] != (not nullable)
                or row[6] != "" or row[7] != ""):
            raise ValueError(f"Contrato RAW divergente: {schema}.{table}.{name}")
    pk_row = connection.execute(
        "SELECT array_agg(a.attname ORDER BY keys.ordinality) "
        "FROM pg_catalog.pg_index i "
        "JOIN pg_catalog.pg_class c ON c.oid=i.indrelid "
        "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
        "CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS keys(attnum,ordinality) "
        "JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum=keys.attnum "
        "WHERE n.nspname=%s AND c.relname=%s AND i.indisprimary AND i.indisvalid AND i.indisready",
        (schema, table)).fetchone()
    if not pk_row or pk_row[0] != [contract.PK]:
        raise ValueError(f"PK RAW divergente: {schema}.{table}")

def prepare(connection, target=("raw", "magento_sales_order")):
    connection.execute(sql.SQL("CREATE TEMP TABLE etl_raw_batch (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP")
                       .format(sql.Identifier(*target)))


def upsert(connection, rows, batch_id, target=("raw", "magento_sales_order"),
           columns=COLUMNS, pk="entity_id", source="magento"):
    all_columns = (*columns, "_source", "_extracted_at", "_batch_id")
    names = sql.SQL(", ").join(map(sql.Identifier, all_columns))
    connection.execute("TRUNCATE pg_temp.etl_raw_batch")
    extracted_at = datetime.now(timezone.utc)
    with connection.cursor() as cursor:
        with cursor.copy(sql.SQL("COPY pg_temp.etl_raw_batch ({}) FROM STDIN").format(names)) as copy:
            for row in rows:
                copy.write_row((*row, source, extracted_at, batch_id))
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c))
            for c in all_columns if c != pk)
        cursor.execute(sql.SQL(
            "INSERT INTO {} ({}) SELECT {} FROM pg_temp.etl_raw_batch WHERE true "
            "ON CONFLICT ({}) DO UPDATE SET {}"
        ).format(sql.Identifier(*target), names, names, sql.Identifier(pk), assignments))
        return cursor.rowcount

from datetime import datetime, timezone

from psycopg import sql
from src.sources.magento.sales_order import COLUMNS

def prepare(connection, target=("raw", "magento_sales_order")):
    connection.execute(sql.SQL("CREATE TEMP TABLE etl_sales_order (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP")
                       .format(sql.Identifier(*target)))


def upsert(connection, rows, batch_id, target=("raw", "magento_sales_order"),
           columns=COLUMNS, pk="entity_id"):
    all_columns = (*columns, "_source", "_extracted_at", "_batch_id")
    names = sql.SQL(", ").join(map(sql.Identifier, all_columns))
    connection.execute("TRUNCATE pg_temp.etl_sales_order")
    extracted_at = datetime.now(timezone.utc)
    with connection.cursor() as cursor:
        with cursor.copy(sql.SQL("COPY pg_temp.etl_sales_order ({}) FROM STDIN").format(names)) as copy:
            for row in rows:
                copy.write_row((*row, "magento", extracted_at, batch_id))
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c))
            for c in all_columns if c != pk)
        cursor.execute(sql.SQL(
            "INSERT INTO {} ({}) SELECT {} FROM pg_temp.etl_sales_order WHERE true "
            "ON CONFLICT ({}) DO UPDATE SET {}"
        ).format(sql.Identifier(*target), names, names, sql.Identifier(pk), assignments))
        return cursor.rowcount

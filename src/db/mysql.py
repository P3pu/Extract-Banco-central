"""Uma transação READ ONLY, TLS e consultas delimitadas por entidade."""

from contextlib import contextmanager
import ssl

import pymysql


class MySQLReader:
    def __init__(self, connection):
        self._connection = connection

    def ping(self):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE()")
            return cursor.fetchone()[0]

    def sales_order_bounds(self, count_total=True):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT @@transaction_isolation, @@session.time_zone")
            isolation, zone = cursor.fetchone()
            if isolation.upper() != "REPEATABLE-READ" or zone != "America/Buenos_Aires":
                raise ValueError("Isolamento ou fuso da origem divergente do contrato")
            aggregate = "COUNT(*)" if count_total else "NULL"
            cursor.execute(f"SELECT {aggregate}, MAX(entity_id), MAX(updated_at) FROM sales_order")
            return cursor.fetchone()

    def sales_order_page(self, **kwargs):
        from src.sources.magento.sales_order import page_query
        query, params = page_query(**kwargs)
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def sales_order_item_bounds(self, count_total=True):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT @@transaction_isolation, @@session.time_zone")
            isolation, zone = cursor.fetchone()
            if isolation.upper() != "REPEATABLE-READ" or zone != "America/Buenos_Aires":
                raise ValueError("Isolamento ou fuso da origem divergente do contrato")
            aggregate = "COUNT(*)" if count_total else "NULL"
            # MAX(updated_at) exigiria uma segunda varredura: obter o watermark
            # das linhas efetivamente extraídas na mesma visão consistente.
            cursor.execute(f"SELECT {aggregate}, MAX(item_id), NULL FROM sales_order_item")
            return cursor.fetchone()

    def sales_order_item_page(self, **kwargs):
        from src.sources.magento.sales_order_item import page_query
        query, params = page_query(**kwargs)
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def ativo_pedido_bounds(self, count_total=True):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT @@tx_isolation, @@session.time_zone, @@system_time_zone")
            isolation, zone, system_zone = cursor.fetchone()
            if isolation.upper() != "REPEATABLE-READ" or (zone != "UTC" and not (zone == "SYSTEM" and system_zone == "UTC")):
                raise ValueError("Isolamento ou fuso do Ativo divergente do contrato")
            aggregate = "COUNT(*)" if count_total else "NULL"
            cursor.execute(f"SELECT {aggregate}, MAX(id_pedido) FROM sa_pedido")
            return cursor.fetchone()

    def ativo_pedido_cutoff(self, days):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT DATE_SUB(NOW(), INTERVAL %s DAY)", (days,))
            return cursor.fetchone()[0]

    def ativo_pedido_page(self, **kwargs):
        from src.sources.ativo.pedido import page_query
        query, params = page_query(**kwargs)
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def ativo_pedido_evento_bounds(self, count_total=True):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT @@tx_isolation, @@session.time_zone, @@system_time_zone")
            isolation, zone, system_zone = cursor.fetchone()
            if isolation.upper() != "REPEATABLE-READ" or (zone != "UTC" and not (zone == "SYSTEM" and system_zone == "UTC")):
                raise ValueError("Isolamento ou fuso do Ativo divergente do contrato")
            aggregate = "COUNT(*)" if count_total else "NULL"
            cursor.execute(f"SELECT {aggregate}, MAX(id_pedido_evento) FROM sa_pedido_evento")
            return cursor.fetchone()

    def ativo_pedido_evento_page(self, **kwargs):
        from src.sources.ativo.pedido_evento import page_query
        query, params = page_query(**kwargs)
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def snapshot_bounds(self, contract, count_total=True):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT @@tx_isolation, @@session.time_zone, @@system_time_zone")
            isolation, zone, system_zone = cursor.fetchone()
            if isolation.upper() != "REPEATABLE-READ" or (zone != "UTC" and not (zone == "SYSTEM" and system_zone == "UTC")):
                raise ValueError("Isolamento ou fuso do Ativo divergente do contrato")
            aggregate = "COUNT(*)" if count_total else "NULL"
            cursor.execute(f"SELECT {aggregate}, MAX(`{contract.PK}`) FROM `{contract.TABLE}`")
            return cursor.fetchone()

    def snapshot_page(self, contract, **kwargs):
        query, params = contract.page_query(**kwargs)
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def recent_user_refs_page(self, column, cutoff, upper_event_id, batch_size, cursor=None):
        if column not in {"id_usuario", "id_usuario_balcao"} or cutoff is None or batch_size <= 0:
            raise ValueError("Consulta de referências inválida")
        where = ["p.dt_pedido >= %s", "pe.id_pedido_evento <= %s",
                 f"pe.`{column}` IS NOT NULL"]
        params = [cutoff, upper_event_id]
        if cursor is not None:
            where.append("pe.id_pedido_evento > %s")
            params.append(cursor)
        params.append(batch_size)
        query = (f"SELECT pe.id_pedido_evento, pe.`{column}` FROM sa_pedido p FORCE INDEX (dt_pedido) "
                 "STRAIGHT_JOIN sa_pedido_evento pe FORCE INDEX (id_pedido) "
                 "ON pe.id_pedido = p.id_pedido "
                 f"WHERE {' AND '.join(where)} ORDER BY pe.id_pedido_evento LIMIT %s")
        with self._connection.cursor() as mysql_cursor:
            mysql_cursor.execute(query, tuple(params))
            return mysql_cursor.fetchall()

    def usuario_ids(self, contract, ids):
        query, params = contract.ids_query(ids)
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def columns(self, database, table):
        with self._connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE, "
                "NUMERIC_PRECISION, NUMERIC_SCALE, CHARACTER_MAXIMUM_LENGTH, ORDINAL_POSITION "
                "FROM information_schema.columns WHERE table_schema=%s AND table_name=%s "
                "ORDER BY ORDINAL_POSITION", (database, table))
            return cursor.fetchall()

    def indexes(self, database, table):
        with self._connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME "
                "FROM information_schema.statistics WHERE table_schema=%s AND table_name=%s "
                "ORDER BY INDEX_NAME, SEQ_IN_INDEX", (database, table))
            return cursor.fetchall()


@contextmanager
def connect(settings, source):
    config = settings.database(source)
    connection = pymysql.connect(
        host=config.host, port=config.port, database=config.database,
        user=config.user, password=config.password, charset="utf8mb4",
        autocommit=False, connect_timeout=settings.connect_timeout,
        read_timeout=60, write_timeout=60,
        ssl=ssl.create_default_context(cafile=settings.env.get("MYSQL_SSL_CA") or None))
    try:
        with connection.cursor() as cursor:
            cursor.execute("START TRANSACTION READ ONLY")
        yield MySQLReader(connection)
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()

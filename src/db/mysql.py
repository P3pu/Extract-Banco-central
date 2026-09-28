"""Uma transação READ ONLY, TLS e interface limitada a SELECT de metadados."""

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

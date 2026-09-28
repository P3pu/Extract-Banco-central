from unittest.mock import MagicMock, patch

import pytest

from src.config.settings import Settings
from src.db import mysql, postgres


def settings():
    return Settings.load({"POSTGRES_HOST": "localhost", "POSTGRES_USER": "user",
                          "POSTGRES_PASSWORD": "secret", "MAGENTO_MYSQL_HOST": "localhost",
                          "MAGENTO_MYSQL_DATABASE": "magento2", "MAGENTO_MYSQL_USER": "user",
                          "MAGENTO_MYSQL_PASSWORD": "secret"})


@pytest.mark.parametrize("fail", [False, True])
def test_mysql_always_read_only_and_rolls_back(fail):
    connection = MagicMock()
    with patch.object(mysql.pymysql, "connect", return_value=connection):
        try:
            with mysql.connect(settings(), "magento"):
                if fail:
                    raise ValueError("simulated")
        except ValueError:
            pass
    connection.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
        "START TRANSACTION READ ONLY")
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()
    connection.commit.assert_not_called()


def test_postgres_rejects_unexpected_server_database():
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = ("other",)
    with patch.object(postgres.psycopg, "connect") as factory:
        factory.return_value.__enter__.return_value = connection
        with pytest.raises(RuntimeError, match="database inesperado"):
            with postgres.connect(settings()):
                pytest.fail("Não deve expor conexão inválida")


def test_failed_ddl_propagates_to_transaction_context():
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = ("Atendimento",)
    connection.execute.side_effect = [connection.execute.return_value, None, ValueError("DDL")]
    with patch.object(postgres.psycopg, "connect") as factory:
        factory.return_value.__enter__.return_value = connection
        factory.return_value.__exit__.return_value = False
        with pytest.raises(ValueError):
            with postgres.connect(settings()) as conn:
                postgres.initialize(conn)
        assert factory.return_value.__exit__.call_args.args[0] is ValueError


def test_metadata_queries_parameterized():
    connection = MagicMock()
    reader = mysql.MySQLReader(connection)
    reader.columns("db", "table'quoted")
    query, params = connection.cursor.return_value.__enter__.return_value.execute.call_args.args
    assert "table'quoted" not in query
    assert params == ("db", "table'quoted")

import pytest

from src.config.settings import ConfigurationError, Settings


def environment():
    return dict(POSTGRES_HOST="localhost", POSTGRES_USER="user",
                POSTGRES_PASSWORD="secret", POSTGRES_DATABASE="Atendimento")


def test_defaults_and_password_not_represented():
    settings = Settings.load(environment())
    assert settings.batch_size == 10000
    assert settings.reconciliation_days == 30
    assert "secret" not in repr(settings)
    assert "secret" not in repr(settings.database("postgres"))


def test_wrong_database_rejected():
    with pytest.raises(ConfigurationError, match="exatamente Atendimento"):
        Settings.load({**environment(), "POSTGRES_DATABASE": "postgres"}).database("postgres")


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.2"])
def test_invalid_batch(value):
    with pytest.raises(ConfigurationError, match="BATCH_SIZE"):
        Settings.load({"BATCH_SIZE": value})


def test_missing_credentials_never_echo_secrets():
    with pytest.raises(ConfigurationError, match="POSTGRES_HOST"):
        Settings.load({"POSTGRES_PASSWORD": "secret"}).database("postgres")


def test_env_password_is_literal(tmp_path, monkeypatch):
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    path = tmp_path / ".env"
    path.write_text("POSTGRES_PASSWORD='abc${SOMETHING}$#@xyz'", encoding="utf-8")
    assert Settings.load(env_file=path).env["POSTGRES_PASSWORD"] == "abc${SOMETHING}$#@xyz"


def test_environment_overrides_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("BATCH_SIZE=50", encoding="utf-8")
    monkeypatch.setenv("BATCH_SIZE", "75")
    assert Settings.load(env_file=path).batch_size == 75


def test_invalid_sslmode_rejected():
    with pytest.raises(ConfigurationError):
        _ = Settings.load({"POSTGRES_SSLMODE": "invalid"}).sslmode

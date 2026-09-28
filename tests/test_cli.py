from src.main import safe_error


def test_diagnostic_redacts_driver_payload():
    assert safe_error(Exception("Access denied for user secret password")) == "autenticação recusada"
    assert "secret" not in safe_error(Exception("unknown payload secret"))

from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from src.core import person_dimension


def test_contact_migration_is_restricted_and_does_not_change_facts():
    sql = person_dimension.MIGRATION.read_text(encoding="utf-8").lower()
    for column in ("cpf text", "nome text", "email text"):
        assert column in sql
    assert "revoke all on core.dim_pessoa, core.pessoa_source_map from public" in sql
    assert "fato_pedido" not in sql
    assert "fato_inscricao" not in sql


def test_schema_absent_does_not_break_existing_automation():
    conn = Mock()
    conn.execute.side_effect = [
        Mock(fetchone=lambda: ("core.dim_pessoa",)),
        [("pessoa_key",), ("cpf_token_seguro",)],
    ]
    assert person_dimension.schema_ready(conn) is False
    assert conn.execute.call_count == 2


def test_partial_contact_schema_fails_closed():
    conn = Mock()
    conn.execute.side_effect = [
        Mock(fetchone=lambda: ("core.dim_pessoa",)),
        [("pessoa_key",), ("cpf",)],
    ]
    with pytest.raises(RuntimeError, match="contato parcial"):
        person_dimension.schema_ready(conn)


def test_contact_schema_requires_versioned_migration(monkeypatch):
    conn = Mock()
    conn.execute.side_effect = [
        Mock(fetchone=lambda: ("core.dim_pessoa",)),
        [("cpf",), ("nome",), ("email",)],
        Mock(fetchone=lambda: None),
    ]
    with pytest.raises(RuntimeError, match="sem registro"):
        person_dimension.schema_ready(conn)


def test_role_merge_never_relabels_buyer_as_runner():
    assert person_dimension._merge_role("COMPRADOR", "PARTICIPANTE") == "AMBOS"
    assert person_dimension._merge_role("PARTICIPANTE", "COMPRADOR") == "AMBOS"


def test_conflicting_document_is_not_silently_relinked():
    conn = Mock()
    conn.execute.side_effect = [
        Mock(fetchone=lambda: (
            44, "111.444.777-35", "SOURCE_ID", "PARTICIPANTE", None, 1,
        )),
        Mock(fetchone=lambda: None),
    ]
    with pytest.raises(RuntimeError, match="revisão de identidade"):
        person_dimension._upsert_profile(
            conn, ("ativo", "Usuario", 77),
            ("123.456.789-09", "Pessoa Sintética", "teste@example.invalid",
             "PARTICIPANTE"), b"k" * 32,
        )
    assert conn.execute.call_count == 2


@pytest.mark.parametrize("value,expected", [
    ("529.982.247-25", "52998224725"),
    ("111.444.777-35", "11144477735"),
    ("529.982.247-24", None),
    ("outro:529.982.247-25", None),
    ("000.000.000-00", None),
    (None, None),
])
def test_cpf_validation_uses_check_digits(value, expected):
    assert person_dimension._valid_cpf(value) == expected


def test_same_valid_cpf_reuses_person_key_and_source_map():
    conn = Mock()
    conn.execute.side_effect = [
        Mock(fetchone=lambda: None),  # Sem mapa para o segundo ID de origem.
        Mock(fetchone=lambda: (44, "529.982.247-25", "CPF_VALIDO", True)),
        Mock(),  # Novo mapa para a pessoa existente.
        Mock(),  # Atualização de contato sem criar pessoa.
    ]
    person_dimension._upsert_profile(
        conn, ("ativo", "Usuario", 77),
        ("529.982.247-25", "Pessoa Sintética", "teste@example.invalid",
         "PARTICIPANTE"), b"k" * 32,
    )
    commands = [call.args[0].lower() for call in conn.execute.call_args_list]
    assert not any("insert into core.dim_pessoa" in sql for sql in commands)
    assert any("insert into core.pessoa_source_map" in sql for sql in commands)


def test_valid_cpf_requires_secret_before_writes():
    conn = Mock()
    with pytest.raises(RuntimeError, match="chave HMAC"):
        person_dimension._upsert_profile(
            conn, ("magento", "Customer", 9),
            ("529.982.247-25", None, None, "COMPRADOR"),
        )
    conn.execute.assert_not_called()


def test_installed_dimension_does_not_sync_automatically_without_gate(monkeypatch):
    monkeypatch.delenv("CORE_PII_ENABLE_SYNC", raising=False)
    monkeypatch.setattr(person_dimension, "schema_ready", lambda _conn: True)
    conn = Mock()
    assert person_dimension.sync_changed(conn, {"magento": {9}}, {}) == {
        "contacts": 0, "installed": True, "enabled": False,
    }
    conn.execute.assert_not_called()


def test_first_valid_cpf_creates_tokenized_person():
    conn = Mock()
    conn.execute.side_effect = [
        Mock(fetchone=lambda: None),  # Source map
        Mock(fetchone=lambda: None),  # Token
        Mock(fetchone=lambda: (44,)),  # New person
        Mock(),  # Source map insert
    ]
    person_dimension._upsert_profile(
        conn, ("magento", "Customer", 9),
        ("529.982.247-25", "Pessoa Sintética", None, "COMPRADOR"),
        b"k" * 32,
    )
    insert = conn.execute.call_args_list[2]
    assert "'CPF_VALIDO'" in insert.args[0]
    assert len(insert.args[1][0]) == 32
    assert b"52998224725" not in insert.args[1][0]


def test_invalid_cpf_keeps_source_identity_without_token():
    conn = Mock()
    conn.execute.side_effect = [
        Mock(fetchone=lambda: None),
        Mock(fetchone=lambda: (45,)),
        Mock(),
    ]
    person_dimension._upsert_profile(
        conn, ("ativo", "Usuario", 77),
        ("529.982.247-24", None, None, "PARTICIPANTE"),
    )
    commands = [call.args[0].lower() for call in conn.execute.call_args_list]
    assert not any("where cpf_token_seguro=%s" in sql for sql in commands)
    assert "'source_id'" in commands[1]


def test_existing_source_is_not_merged_into_another_person_automatically():
    conn = Mock()
    conn.execute.side_effect = [
        Mock(fetchone=lambda: (44, None, "SOURCE_ID", "COMPRADOR", None, 1)),
        Mock(fetchone=lambda: (55, "52998224725", "CPF_VALIDO", True)),
    ]
    with pytest.raises(RuntimeError, match="outra pessoa_key"):
        person_dimension._upsert_profile(
            conn, ("magento", "Customer", 9),
            ("529.982.247-25", None, None, "COMPRADOR"), b"k" * 32,
        )
    assert conn.execute.call_count == 2


def test_bulk_valid_profiles_use_temp_table_and_set_based_upsert():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (0,)
    conn.execute.return_value.fetchall.return_value = []
    profile = {("magento", "Customer", 9):
               ("529.982.247-25", "Pessoa Sintética", None, "COMPRADOR")}
    person_dimension._bulk_upsert_profiles(conn, profile, b"k" * 32)
    sql = "\n".join(call.args[0].lower()
                    for call in conn.execute.call_args_list)
    assert "create temp table pg_temp.core_person_profile_batch" in sql
    assert "on commit drop" in sql
    assert "on conflict do nothing" in sql
    assert "insert into core.pessoa_source_map" in sql
    assert "update core.dim_pessoa" in sql
    row = conn.cursor.return_value.copy.return_value.__enter__.return_value.write_row
    row.assert_called_once()
    assert len(row.call_args.args[0][-2]) == 32


def test_today_export_reads_only_core_and_keeps_null_contacts():
    sql = (Path(__file__).resolve().parents[1]
           / "sql/core/v1/920_pessoas_hoje_readonly.sql").read_text(encoding="utf-8")
    lower = sql.lower()
    assert "begin read only" in lower
    assert "america/sao_paulo" in lower
    assert "core.dim_pessoa" in lower
    assert "core.fato_pedido" in lower
    assert "core.fato_inscricao" in lower
    assert "staging." not in lower and "raw." not in lower
    assert 'AS "Nome"' in sql and 'AS "E-mail"' in sql and 'AS "CPF"' in sql

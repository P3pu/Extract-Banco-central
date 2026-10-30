"""Materializa contatos de IDs de origem comprovados na dim_pessoa.

Nunca registra PII em logs. Une origens somente por CPF com dígitos
verificadores válidos e token HMAC; sem CPF válido, conserva o ID de origem.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime
import hashlib
import hmac
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

import psycopg

CONTACT_COLUMNS = {"cpf", "nome", "email"}
CHUNK_SIZE = 1000
MIGRATION = (Path(__file__).resolve().parents[2]
             / "sql/core/v1/008_dim_pessoa_contato.sql")
SOURCE_CONTRACT = {
    ("staging", "magento_cliente"):
        {"cliente_id", "documento", "primeiro_nome", "sobrenome", "email"},
    ("staging", "ativo_usuario"):
        {"usuario_id", "documento", "nome", "sobrenome", "email"},
    ("staging", "ativo_usuario_balcao"):
        {"usuario_balcao_id", "documento", "nome", "email"},
    ("staging", "magento_inscricao"):
        {"inscricao_id", "cliente_id", "cliente_ambiguo"},
    ("staging", "magento_item_cliente"):
        {"item_id", "cliente_id", "cliente_ambiguo"},
    ("core", "fato_pedido"):
        {"origem", "pedido_id_origem", "comprador_id_origem", "comprador_key"},
    ("core", "fato_inscricao"):
        {"origem", "inscricao_id_origem", "participante_id_origem",
         "participante_namespace_origem", "participante_key"},
}


def migration_digest() -> str:
    return hashlib.sha256(MIGRATION.read_bytes()).hexdigest()


def source_contract_ready(conn) -> bool:
    rows = conn.execute("""
        SELECT table_schema,table_name,column_name
        FROM information_schema.columns
        WHERE table_schema IN ('core','staging')
    """).fetchall()
    actual = defaultdict(set)
    for schema, table, column in rows:
        actual[schema, table].add(column)
    return all(columns <= actual[key] for key, columns in SOURCE_CONTRACT.items())


def schema_ready(conn) -> bool:
    if conn.execute("SELECT to_regclass('core.dim_pessoa')").fetchone()[0] is None:
        raise RuntimeError("CORE ausente")
    columns = {name for (name,) in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='core' AND table_name='dim_pessoa'"
    )}
    present = CONTACT_COLUMNS & columns
    if not present:
        return False  # Migração PII ainda não aplicada: não interromper a RAW/CORE.
    if present != CONTACT_COLUMNS:
        raise RuntimeError("SCHEMA_DIVERGENTE: dim_pessoa contato parcial")
    row = conn.execute(
        "SELECT sha256 FROM core.schema_migration WHERE migration_id=%s",
        (MIGRATION.name,),
    ).fetchone()
    if row is None or row[0] != migration_digest():
        raise RuntimeError("SCHEMA_DIVERGENTE: migração de contato sem registro")
    return True


def apply_migration(conn) -> bool:
    """Aplica só 008, atômica com o registro; não chama migrações anteriores."""
    if conn.execute("SELECT current_database()").fetchone()[0] != "Atendimento":
        raise RuntimeError("Destino PostgreSQL inesperado")
    if conn.execute("SELECT to_regclass('core.schema_migration')").fetchone()[0] is None:
        raise RuntimeError("CORE/schema_migration ausente")
    if not source_contract_ready(conn):
        raise RuntimeError("Contrato CORE/STAGING de pessoas incompatível")
    other_readers = conn.execute("""
        SELECT COUNT(*)
        FROM pg_class c
        CROSS JOIN LATERAL aclexplode(
            COALESCE(c.relacl, acldefault('r', c.relowner))) grant_item
        WHERE c.oid='core.dim_pessoa'::regclass
          AND grant_item.privilege_type='SELECT'
          AND grant_item.grantee<>c.relowner
    """).fetchone()[0]
    if other_readers:
        raise RuntimeError("dim_pessoa possui leitores adicionais; revisar grants")
    global_readers = conn.execute("""
        SELECT COUNT(*) FROM pg_roles r
        WHERE r.rolname NOT IN (current_user, 'pg_read_all_data')
          AND pg_has_role(r.oid, 'pg_read_all_data', 'member')
    """).fetchone()[0]
    if global_readers:
        raise RuntimeError("Papéis com pg_read_all_data exigem revisão de acesso")
    columns = {name for (name,) in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='core' AND table_name='dim_pessoa'"
    )}
    row = conn.execute(
        "SELECT sha256 FROM core.schema_migration WHERE migration_id=%s",
        (MIGRATION.name,),
    ).fetchone()
    if row is not None:
        if row[0] != migration_digest() or not CONTACT_COLUMNS <= columns:
            raise RuntimeError("Migração de contato divergente")
        return False
    if CONTACT_COLUMNS & columns:
        raise RuntimeError("Migração de contato parcialmente aplicada")
    with conn.transaction():
        conn.execute(MIGRATION.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO core.schema_migration(migration_id,sha256) VALUES (%s,%s)",
            (MIGRATION.name, migration_digest()),
        )
    return True


def _chunks(values):
    sorted_values = sorted({int(value) for value in values if value is not None})
    if any(value < 0 for value in sorted_values):
        raise ValueError("ID de origem inválido")
    for start in range(0, len(sorted_values), CHUNK_SIZE):
        yield sorted_values[start:start + CHUNK_SIZE]


def _cpf_digits(value):
    return "".join(char for char in (value or "") if char in "0123456789")


def _valid_cpf(value):
    if value is None or re.fullmatch(r"[0-9.\-\s]+", value) is None:
        return None
    digits = _cpf_digits(value)
    if len(digits) != 11 or len(set(digits)) == 1:
        return None
    for length in (9, 10):
        weight = length + 1
        check = (sum(int(digit) * (weight - index)
                     for index, digit in enumerate(digits[:length])) * 10) % 11
        if (0 if check == 10 else check) != int(digits[length]):
            return None
    return digits


def _hmac_key():
    path = os.environ.get("CORE_PII_HMAC_KEY_FILE")
    if not path and os.environ.get("BCD_STATE_DIR"):
        path = str(Path(os.environ["BCD_STATE_DIR"]) / "core-person-hmac.key")
    if not path:
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            raise RuntimeError("Chave HMAC de CPF não provisionada")
        path = str(Path(base) / "BancoCentralDados" / "core-person-hmac.key")
    key_path = Path(path).expanduser().resolve(strict=True)
    if key_path.is_relative_to(Path(__file__).resolve().parents[2]):
        raise RuntimeError("Chave HMAC não pode ficar no repositório")
    raw = key_path.read_text(encoding="ascii").strip()
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise RuntimeError("Formato da chave HMAC inválido") from exc
    if len(key) < 32:
        raise RuntimeError("Chave HMAC deve ter ao menos 32 bytes")
    return key


def _cpf_token(digits, key):
    return hmac.new(key, b"bcd-core-person-v1:" + digits.encode("ascii"),
                    hashlib.sha256).digest()


def _verify_key(conn, key, sample=100):
    """Recusa chave diferente da que gerou os tokens gravados (evita duplicar pessoas)."""
    rows = conn.execute("""
        SELECT cpf,cpf_token_seguro FROM core.dim_pessoa
        WHERE criterio_identificacao='CPF_VALIDO' ORDER BY pessoa_key LIMIT %s
    """, (sample,)).fetchall()
    for cpf, token in rows:
        digits = _valid_cpf(cpf)
        if digits is None or not hmac.compare_digest(_cpf_token(digits, key), bytes(token)):
            raise RuntimeError("Chave HMAC diverge dos tokens gravados")


def rotate_key(conn, key):
    """Recalcula todos os tokens de CPF com a chave atual, numa transação.

    Usa o CPF guardado na própria dim_pessoa; pessoa_key e vínculos não mudam.
    """
    with conn.transaction():
        conn.execute("LOCK TABLE core.dim_pessoa IN SHARE ROW EXCLUSIVE MODE")
        rows = conn.execute("""
            SELECT pessoa_key,cpf FROM core.dim_pessoa
            WHERE criterio_identificacao='CPF_VALIDO'
        """).fetchall()
        tokens = {}
        for person_key, cpf in rows:
            digits = _valid_cpf(cpf)
            if digits is None:
                raise RuntimeError("CPF validado ausente ou vínculo compartilhado; revisão necessária")
            tokens[person_key] = _cpf_token(digits, key)
        if len(set(tokens.values())) != len(tokens):
            raise RuntimeError("Token de CPF existente divergente")
        conn.execute("CREATE TEMP TABLE core_person_rotation "
                     "(pessoa_key BIGINT PRIMARY KEY, token BYTEA NOT NULL) ON COMMIT DROP")
        with conn.cursor().copy("COPY pg_temp.core_person_rotation FROM STDIN") as copy:
            for row in tokens.items():
                copy.write_row(row)
        # Chave nova é independente da antiga: colisão de 256 bits com um
        # token antigo não é um cenário real; o índice único recusaria.
        updated = conn.execute("""
            UPDATE core.dim_pessoa d SET cpf_token_seguro=r.token
            FROM pg_temp.core_person_rotation r WHERE d.pessoa_key=r.pessoa_key
        """).rowcount
        if updated != len(tokens):
            raise RuntimeError("Rotação parcial da chave HMAC")
        _verify_key(conn, key)
    return updated


def _merge_role(current, incoming):
    if current is None or current == incoming:
        return incoming
    return "AMBOS"


def _source_profiles(conn, orders, inscriptions):
    profiles = {}

    def add(row):
        origin, namespace, source_id, cpf, name, email, role = row
        if source_id is None or source_id <= 0:
            return
        key = (origin, namespace, source_id)
        previous = profiles.get(key)
        if previous is not None and previous[:3] != (cpf, name, email):
            raise RuntimeError("SCHEMA_DIVERGENTE: cadastro de origem ambíguo")
        profiles[key] = (cpf, name, email,
                         _merge_role(previous[3] if previous else None, role))

    for ids in _chunks(orders.get("magento", ())):
        rows = conn.execute("""
            SELECT DISTINCT 'magento','Customer',c.cliente_id,c.documento,
                   NULLIF(BTRIM(CONCAT_WS(' ',c.primeiro_nome,c.sobrenome)),''),
                   c.email,'COMPRADOR'
            FROM core.fato_pedido p
            JOIN staging.magento_cliente c ON c.cliente_id=p.comprador_id_origem
            WHERE p.origem='magento' AND p.pedido_id_origem=ANY(%s::bigint[])
              AND c.cliente_id>0
        """, (ids,)).fetchall()
        for row in rows:
            add(row)

    # Comprador Ativo = usuário do pedido. A mesma pessoa pode ser
    # participante de outros pedidos; o CPF une os papéis (AMBOS).
    for ids in _chunks(orders.get("ativo", ())):
        rows = conn.execute("""
            SELECT DISTINCT 'ativo','Usuario',u.usuario_id,u.documento,
                   NULLIF(BTRIM(CONCAT_WS(' ',u.nome,u.sobrenome)),''),
                   u.email,'COMPRADOR'
            FROM core.fato_pedido p
            JOIN staging.ativo_usuario u ON u.usuario_id=p.comprador_id_origem
            WHERE p.origem='ativo' AND p.pedido_id_origem=ANY(%s::bigint[])
              AND u.usuario_id>0
        """, (ids,)).fetchall()
        for row in rows:
            add(row)

    for ids in _chunks(inscriptions.get("ativo", ())):
        rows = conn.execute("""
            WITH selecionadas AS (
                SELECT participante_namespace_origem,participante_id_origem
                FROM core.fato_inscricao
                WHERE origem='ativo' AND inscricao_id_origem=ANY(%s::bigint[])
            )
            SELECT DISTINCT 'ativo','Usuario',u.usuario_id,u.documento,
                   NULLIF(BTRIM(CONCAT_WS(' ',u.nome,u.sobrenome)),''),
                   u.email,'PARTICIPANTE'
            FROM selecionadas f JOIN staging.ativo_usuario u
              ON f.participante_namespace_origem='Usuario'
             AND u.usuario_id=f.participante_id_origem
            WHERE u.usuario_id>0
            UNION
            SELECT DISTINCT 'ativo','UsuarioBalcao',b.usuario_balcao_id,
                   b.documento,b.nome,b.email,'PARTICIPANTE'
            FROM selecionadas f JOIN staging.ativo_usuario_balcao b
              ON f.participante_namespace_origem='UsuarioBalcao'
             AND b.usuario_balcao_id=f.participante_id_origem
            WHERE b.usuario_balcao_id>0
        """, (ids,)).fetchall()
        for row in rows:
            add(row)

    cache = conn.execute(
        "SELECT to_regclass('pg_temp.core_v1_magento_inscricao_cache')"
    ).fetchone()[0]
    relation = ("pg_temp.core_v1_magento_inscricao_cache" if cache is not None
                else "staging.magento_item_cliente")
    item_id_column = "inscricao_id" if cache is not None else "item_id"
    for ids in _chunks(inscriptions.get("magento", ())):
        # A relação é uma constante interna, nunca entrada do usuário.
        rows = conn.execute(f"""
            SELECT DISTINCT 'magento','Customer',c.cliente_id,c.documento,
                   NULLIF(BTRIM(CONCAT_WS(' ',c.primeiro_nome,c.sobrenome)),''),
                   c.email,'PARTICIPANTE'
            FROM core.fato_inscricao f
            JOIN {relation} i ON i.{item_id_column}=f.inscricao_id_origem
            JOIN staging.magento_cliente c ON c.cliente_id=i.cliente_id
            WHERE f.origem='magento' AND f.inscricao_id_origem=ANY(%s::bigint[])
              AND i.{item_id_column}=ANY(%s::bigint[])
              AND i.cliente_ambiguo IS FALSE AND c.cliente_id>0
        """, (ids, ids)).fetchall()
        for row in rows:
            add(row)
    return profiles, relation, item_id_column


def _upsert_profile(conn, key, contact, hmac_key=None):
    origin, namespace, source_id = key
    cpf, name, email, role = contact
    digits = _valid_cpf(cpf)
    if digits is not None and hmac_key is None:
        raise RuntimeError("CPF válido requer chave HMAC provisionada")
    token = _cpf_token(digits, hmac_key) if digits is not None else None
    existing = conn.execute("""
        SELECT m.pessoa_key,d.cpf,d.criterio_identificacao,m.papel_verificado,
               d.cpf_token_seguro,
               (SELECT COUNT(*) FROM core.pessoa_source_map other
                WHERE other.pessoa_key=m.pessoa_key)
        FROM core.pessoa_source_map m
        JOIN core.dim_pessoa d ON d.pessoa_key=m.pessoa_key
        WHERE m.origem=%s AND m.tipo_identificador=%s AND m.id_pessoa_origem=%s
        FOR UPDATE OF d
    """, (origin, namespace, source_id)).fetchone()
    target = None
    if token is not None:
        target = conn.execute("""
            SELECT pessoa_key,cpf,criterio_identificacao,cpf_valido
            FROM core.dim_pessoa WHERE cpf_token_seguro=%s FOR UPDATE
        """, (token,)).fetchone()
        if target is not None and (
            target[2] != "CPF_VALIDO" or target[3] is not True
            or _valid_cpf(target[1]) != digits
        ):
            raise RuntimeError("Token de CPF existente divergente")

    if existing is None:
        if target is None:
            if token is None:
                person_key = conn.execute("""
                    INSERT INTO core.dim_pessoa
                        (criterio_identificacao,cpf_valido,cpf,nome,email)
                    VALUES ('SOURCE_ID',%s,%s,%s,%s) RETURNING pessoa_key
                """, (False if cpf else None, cpf, name, email)).fetchone()[0]
            else:
                person_key = conn.execute("""
                    INSERT INTO core.dim_pessoa
                        (criterio_identificacao,cpf_valido,cpf_token_seguro,
                         cpf,nome,email)
                    VALUES ('CPF_VALIDO',TRUE,%s,%s,%s,%s) RETURNING pessoa_key
                """, (token, cpf, name, email)).fetchone()[0]
        else:
            person_key = target[0]
        conn.execute("""
            INSERT INTO core.pessoa_source_map
                (origem,tipo_identificador,id_pessoa_origem,pessoa_key,
                 papel_verificado,criterio_vinculo,flag_ambiguidade)
            VALUES (%s,%s,%s,%s,%s,%s,FALSE)
        """, (origin, namespace, source_id, person_key, role,
              "CPF_VALIDO" if token is not None else "SOURCE_ID"))
        if target is None:
            return
        old_role = role
    else:
        person_key, old_cpf, criterion, old_role, old_token, map_count = existing
        old_valid = _valid_cpf(old_cpf)
        if old_valid is not None and old_valid != digits:
            raise RuntimeError("CPF de origem alterado; revisão de identidade necessária")
        if token is not None:
            if target is not None and target[0] != person_key:
                raise RuntimeError("CPF já pertence a outra pessoa_key; revisão necessária")
            if criterion == "SOURCE_ID" and map_count == 1:
                conn.execute("""
                    UPDATE core.dim_pessoa
                    SET criterio_identificacao='CPF_VALIDO',cpf_valido=TRUE,
                        cpf_token_seguro=%s,cpf=%s,nome=COALESCE(%s,nome),
                        email=COALESCE(%s,email),
                        atualizado_core_em=clock_timestamp()
                    WHERE pessoa_key=%s
                """, (token, cpf, name, email, person_key))
                conn.execute("""
                    UPDATE core.pessoa_source_map SET criterio_vinculo='CPF_VALIDO'
                    WHERE origem=%s AND tipo_identificador=%s AND id_pessoa_origem=%s
                """, (origin, namespace, source_id))
            elif criterion != "CPF_VALIDO" or old_token != token:
                raise RuntimeError("Vínculo de CPF divergente; revisão necessária")
        elif criterion != "SOURCE_ID" or map_count != 1:
            raise RuntimeError("CPF validado ausente ou vínculo compartilhado; revisão necessária")

    if token is not None:
        # Um CPF válido pode ter vários IDs de origem; contato preenchido não
        # é apagado por NULL de outra origem. Ordem de IDs é determinística.
        conn.execute("""
            UPDATE core.dim_pessoa
            SET cpf=COALESCE(%s,cpf),nome=COALESCE(%s,nome),
                email=COALESCE(%s,email),atualizado_core_em=clock_timestamp()
            WHERE pessoa_key=%s
              AND (cpf,nome,email) IS DISTINCT FROM
                  (COALESCE(%s,cpf),COALESCE(%s,nome),COALESCE(%s,email))
        """, (cpf, name, email, person_key, cpf, name, email))
    else:
        conn.execute("""
            UPDATE core.dim_pessoa
            SET cpf=%s,nome=%s,email=%s,cpf_valido=%s,
                atualizado_core_em=clock_timestamp()
            WHERE pessoa_key=%s AND (cpf,nome,email,cpf_valido)
                IS DISTINCT FROM (%s,%s,%s,%s)
        """, (cpf, name, email, False if cpf else None, person_key,
              cpf, name, email, False if cpf else None))
    new_role = _merge_role(old_role, role)
    if new_role != old_role:
        conn.execute("UPDATE core.pessoa_source_map SET papel_verificado=%s "
                     "WHERE origem=%s AND tipo_identificador=%s "
                     "AND id_pessoa_origem=%s",
                     (new_role, origin, namespace, source_id))


def _bulk_upsert_profiles(conn, profiles, hmac_key):
    """Um lote transacional: CPFs válidos em SQL set-based, exceções por ID."""
    if not profiles:
        return
    conn.execute("""
        CREATE TEMP TABLE pg_temp.core_person_profile_batch (
            origem TEXT NOT NULL,
            tipo_identificador TEXT NOT NULL,
            id_pessoa_origem BIGINT NOT NULL,
            cpf TEXT, nome TEXT, email TEXT, papel TEXT NOT NULL,
            cpf_token BYTEA, cpf_digits TEXT,
            PRIMARY KEY (origem,tipo_identificador,id_pessoa_origem)
        ) ON COMMIT DROP
    """)
    with conn.cursor().copy("""
        COPY pg_temp.core_person_profile_batch
          (origem,tipo_identificador,id_pessoa_origem,cpf,nome,email,papel,
           cpf_token,cpf_digits) FROM STDIN
    """) as writer:
        for (origin, namespace, source_id), (cpf, name, email, role) in sorted(
            profiles.items()
        ):
            digits = _valid_cpf(cpf)
            token = _cpf_token(digits, hmac_key) if digits is not None else None
            writer.write_row((origin, namespace, source_id, cpf, name, email,
                              role, token, digits))

    conflicts = conn.execute("""
        SELECT COUNT(*) FROM pg_temp.core_person_profile_batch b
        JOIN core.pessoa_source_map m
          ON m.origem=b.origem
         AND m.tipo_identificador=b.tipo_identificador
         AND m.id_pessoa_origem=b.id_pessoa_origem
        JOIN core.dim_pessoa d ON d.pessoa_key=m.pessoa_key
        WHERE (b.cpf_token IS NOT NULL AND
               d.cpf_token_seguro IS DISTINCT FROM b.cpf_token)
           OR (b.cpf_token IS NULL AND d.criterio_identificacao<>'SOURCE_ID')
    """).fetchone()[0]
    if conflicts:
        raise RuntimeError("Vínculos existentes exigem revisão de identidade")
    collision = conn.execute("""
        SELECT COUNT(*) FROM pg_temp.core_person_profile_batch b
        JOIN core.dim_pessoa d ON d.cpf_token_seguro=b.cpf_token
        WHERE b.cpf_token IS NOT NULL
          AND REGEXP_REPLACE(COALESCE(d.cpf,''),'[^0-9]','','g')<>b.cpf_digits
    """).fetchone()[0]
    if collision:
        raise RuntimeError("Token de CPF existente divergente")

    conn.execute("""
        INSERT INTO core.dim_pessoa
            (criterio_identificacao,cpf_valido,cpf_token_seguro,cpf,nome,email)
        SELECT DISTINCT ON (cpf_token)
            'CPF_VALIDO',TRUE,cpf_token,cpf,nome,email
        FROM pg_temp.core_person_profile_batch
        WHERE cpf_token IS NOT NULL
        ORDER BY cpf_token,origem,tipo_identificador,id_pessoa_origem
        ON CONFLICT DO NOTHING
    """)
    conn.execute("""
        INSERT INTO core.pessoa_source_map
            (origem,tipo_identificador,id_pessoa_origem,pessoa_key,
             papel_verificado,criterio_vinculo,flag_ambiguidade)
        SELECT b.origem,b.tipo_identificador,b.id_pessoa_origem,d.pessoa_key,
               b.papel,'CPF_VALIDO',FALSE
        FROM pg_temp.core_person_profile_batch b
        JOIN core.dim_pessoa d ON d.cpf_token_seguro=b.cpf_token
        WHERE b.cpf_token IS NOT NULL
        ON CONFLICT (origem,tipo_identificador,id_pessoa_origem) DO NOTHING
    """)
    conn.execute("""
        UPDATE core.pessoa_source_map m
        SET papel_verificado=CASE
            WHEN m.papel_verificado IS NULL THEN b.papel
            WHEN m.papel_verificado=b.papel THEN m.papel_verificado
            ELSE 'AMBOS' END
        FROM pg_temp.core_person_profile_batch b
        WHERE b.cpf_token IS NOT NULL
          AND m.origem=b.origem
          AND m.tipo_identificador=b.tipo_identificador
          AND m.id_pessoa_origem=b.id_pessoa_origem
          AND m.papel_verificado IS DISTINCT FROM b.papel
    """)
    conn.execute("""
        WITH contact AS (
            SELECT cpf_token,
                   (ARRAY_AGG(cpf ORDER BY origem,tipo_identificador,
                              id_pessoa_origem DESC)
                    FILTER (WHERE cpf IS NOT NULL))[1] AS cpf,
                   (ARRAY_AGG(nome ORDER BY origem,tipo_identificador,
                              id_pessoa_origem DESC)
                    FILTER (WHERE nome IS NOT NULL))[1] AS nome,
                   (ARRAY_AGG(email ORDER BY origem,tipo_identificador,
                              id_pessoa_origem DESC)
                    FILTER (WHERE email IS NOT NULL))[1] AS email
            FROM pg_temp.core_person_profile_batch
            WHERE cpf_token IS NOT NULL GROUP BY cpf_token
        )
        UPDATE core.dim_pessoa d
        SET cpf=COALESCE(c.cpf,d.cpf),nome=COALESCE(c.nome,d.nome),
            email=COALESCE(c.email,d.email),
            atualizado_core_em=clock_timestamp()
        FROM contact c WHERE d.cpf_token_seguro=c.cpf_token
          AND (d.cpf,d.nome,d.email) IS DISTINCT FROM
              (COALESCE(c.cpf,d.cpf),COALESCE(c.nome,d.nome),
               COALESCE(c.email,d.email))
    """)
    invalid = conn.execute("""
        SELECT origem,tipo_identificador,id_pessoa_origem,cpf,nome,email,papel
        FROM pg_temp.core_person_profile_batch WHERE cpf_token IS NULL
        ORDER BY origem,tipo_identificador,id_pessoa_origem
    """).fetchall()
    for origin, namespace, source_id, cpf, name, email, role in invalid:
        _upsert_profile(conn, (origin, namespace, source_id),
                        (cpf, name, email, role))


def sync_changed(conn, orders, inscriptions) -> dict[str, int | bool]:
    """Atualiza só IDs modificados; chamar em transação após os fatos CORE."""
    if not schema_ready(conn):
        return {"contacts": 0, "installed": False, "enabled": False}
    if os.environ.get("CORE_PII_ENABLE_SYNC") != "approved":
        return {"contacts": 0, "installed": True, "enabled": False}
    profiles, magento_relation, item_id_column = _source_profiles(
        conn, orders, inscriptions)
    hmac_key = _hmac_key() if any(_valid_cpf(contact[0])
                                  for contact in profiles.values()) else None
    if hmac_key is not None:
        _verify_key(conn, hmac_key)
    _bulk_upsert_profiles(conn, profiles, hmac_key)

    for ids in _chunks(orders.get("magento", ())):
        conn.execute("""
            UPDATE core.fato_pedido p SET comprador_key=m.pessoa_key
            FROM core.pessoa_source_map m
            WHERE p.origem='magento' AND p.pedido_id_origem=ANY(%s::bigint[])
              AND m.origem='magento' AND m.tipo_identificador='Customer'
              AND m.id_pessoa_origem=p.comprador_id_origem
              AND p.comprador_key IS DISTINCT FROM m.pessoa_key
        """, (ids,))
    for ids in _chunks(orders.get("ativo", ())):
        conn.execute("""
            UPDATE core.fato_pedido p SET comprador_key=m.pessoa_key
            FROM core.pessoa_source_map m
            WHERE p.origem='ativo' AND p.pedido_id_origem=ANY(%s::bigint[])
              AND m.origem='ativo' AND m.tipo_identificador='Usuario'
              AND m.id_pessoa_origem=p.comprador_id_origem
              AND p.comprador_key IS DISTINCT FROM m.pessoa_key
        """, (ids,))
    for ids in _chunks(inscriptions.get("ativo", ())):
        conn.execute("""
            UPDATE core.fato_inscricao f SET participante_key=m.pessoa_key
            FROM core.pessoa_source_map m
            WHERE f.origem='ativo' AND f.inscricao_id_origem=ANY(%s::bigint[])
              AND m.origem='ativo'
              AND m.tipo_identificador=f.participante_namespace_origem
              AND m.id_pessoa_origem=f.participante_id_origem
              AND f.participante_key IS DISTINCT FROM m.pessoa_key
        """, (ids,))
    for ids in _chunks(inscriptions.get("magento", ())):
        conn.execute(f"""
            UPDATE core.fato_inscricao f SET participante_key=m.pessoa_key
            FROM {magento_relation} i JOIN core.pessoa_source_map m
              ON m.origem='magento' AND m.tipo_identificador='Customer'
             AND m.id_pessoa_origem=i.cliente_id
            WHERE f.origem='magento' AND f.inscricao_id_origem=ANY(%s::bigint[])
              AND i.{item_id_column}=f.inscricao_id_origem
              AND i.{item_id_column}=ANY(%s::bigint[])
              AND i.cliente_ambiguo IS FALSE
              AND f.participante_key IS DISTINCT FROM m.pessoa_key
        """, (ids, ids))
    return {"contacts": len(profiles), "installed": True, "enabled": True}


def backfill_since(conn, since: date, maximum: int = 1000,
                   until: date | None = None) -> dict[str, int]:
    """Preenche contatos de um período, com limite e transação por chamada.

    Não faz varredura histórica ilimitada. Inscrições em pedidos anteriores
    ficam fora deste backfill e exigem reconciliação separada.
    """
    if not schema_ready(conn):
        raise RuntimeError("Migração 008 não aplicada")
    if os.environ.get("CORE_PII_ENABLE_SYNC") != "approved":
        raise RuntimeError("Gate de sincronização PII fechado")
    if maximum < 1 or maximum > 10000:
        raise ValueError("Limite de backfill inválido")
    if until is not None and until <= since:
        raise ValueError("Fim do período deve ser posterior ao início")
    end_filter = "AND data_pedido < %s" if until is not None else ""
    args = (since, until, maximum + 1) if until is not None else (since, maximum + 1)
    order_rows = conn.execute(f"""
        SELECT origem,pedido_id_origem FROM core.fato_pedido
        WHERE origem IN ('ativo','magento') AND data_pedido >= %s {end_filter}
        ORDER BY origem,pedido_id_origem LIMIT %s
    """, args).fetchall()
    if len(order_rows) > maximum:
        raise RuntimeError("Backfill de pedidos excede limite aprovado")
    orders = defaultdict(set)
    for origin, source_id in order_rows:
        orders[origin].add(source_id)
    end_filter = "AND p.data_pedido < %s" if until is not None else ""
    inscription_rows = conn.execute(f"""
        SELECT f.origem,f.inscricao_id_origem
        FROM core.fato_inscricao f
        JOIN core.fato_pedido p
          ON p.origem=f.origem AND p.pedido_id_origem=f.pedido_id_origem
        WHERE p.origem IN ('ativo','magento') AND p.data_pedido >= %s {end_filter}
        ORDER BY f.origem,f.inscricao_id_origem LIMIT %s
    """, args).fetchall()
    if len(inscription_rows) > maximum:
        raise RuntimeError("Backfill de inscrições excede limite aprovado")
    inscriptions = defaultdict(set)
    for origin, source_id in inscription_rows:
        inscriptions[origin].add(source_id)
    with conn.transaction():
        result = sync_changed(conn, orders, inscriptions)
    return {"orders": len(order_rows), "inscriptions": len(inscription_rows),
            "contacts": int(result["contacts"])}


def plan_since(conn, since: date) -> dict[str, tuple[float, int]]:
    """Estima custo sem executar SELECT de dados ou modificar o banco."""
    queries = {
        "orders": """
            SELECT origem,pedido_id_origem FROM core.fato_pedido
            WHERE origem IN ('ativo','magento') AND data_pedido >= %s
            ORDER BY origem,pedido_id_origem
        """,
        "inscriptions": """
            SELECT f.origem,f.inscricao_id_origem
            FROM core.fato_inscricao f JOIN core.fato_pedido p
              ON p.origem=f.origem AND p.pedido_id_origem=f.pedido_id_origem
            WHERE p.origem IN ('ativo','magento') AND p.data_pedido >= %s
            ORDER BY f.origem,f.inscricao_id_origem
        """,
    }
    result = {}
    for scope, query in queries.items():
        plan = conn.execute("EXPLAIN (FORMAT JSON) " + query,
                            (since,)).fetchone()[0][0]["Plan"]
        result[scope] = (float(plan["Total Cost"]), int(plan["Plan Rows"]))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Contatos restritos da dim_pessoa")
    parser.add_argument("command", choices=("inspect", "plan", "migrate", "backfill",
                                            "rotate-key"))
    parser.add_argument("--since", type=date.fromisoformat)
    parser.add_argument("--until", type=date.fromisoformat,
                        help="Fim exclusivo do período de backfill")
    parser.add_argument("--max-ids", type=int, default=1000)
    parser.add_argument("--approve-production", action="store_true")
    args = parser.parse_args(argv)
    if args.command not in ("inspect", "plan") and not (
        args.approve_production and
        os.environ.get("CORE_PII_APPROVAL") == "DIM_PESSOA_PII_APPROVED"
    ):
        parser.error("migração/backfill requer aprovação operacional explícita")

    # Mesmo caminho de túnel dedicado da automação; nenhuma senha em argv/log.
    from src.automation.local_raw_core import LOCK_ID, local_settings, postgres_access

    try:
        settings = local_settings()
        pg = settings.database("postgres")
        with postgres_access(settings):
            with psycopg.connect(
                host=pg.host, port=pg.port, dbname=pg.database,
                user=pg.user, password=pg.password, sslmode="disable",
                connect_timeout=10, autocommit=True,
                application_name="bcd-core-person-dim",
                options="-c statement_timeout=120000 -c lock_timeout=5000",
            ) as conn:
                if conn.execute("SELECT current_database()").fetchone()[0] != "Atendimento":
                    raise RuntimeError("Destino PostgreSQL inesperado")
                if args.command == "plan":
                    since = args.since or datetime.now(
                        ZoneInfo("America/Sao_Paulo")).date()
                    estimates = plan_since(conn, since)
                    print(f"CORE_PERSON_PLAN since={since} "
                          f"orders_rows_est={estimates['orders'][1]} "
                          f"orders_cost={estimates['orders'][0]:.0f} "
                          f"inscriptions_rows_est={estimates['inscriptions'][1]} "
                          f"inscriptions_cost={estimates['inscriptions'][0]:.0f}")
                elif args.command == "inspect":
                    installed = schema_ready(conn)
                    contract = source_contract_ready(conn)
                    ledger = conn.execute(
                        "SELECT to_regclass('core.schema_migration') IS NOT NULL"
                    ).fetchone()[0]
                    direct_readers = conn.execute("""
                        SELECT COUNT(*) FROM pg_class c
                        CROSS JOIN LATERAL aclexplode(
                            COALESCE(c.relacl,acldefault('r',c.relowner))) a
                        WHERE c.oid='core.dim_pessoa'::regclass
                          AND a.privilege_type='SELECT' AND a.grantee<>c.relowner
                    """).fetchone()[0]
                    global_readers = conn.execute("""
                        SELECT COUNT(*) FROM pg_roles r
                        WHERE r.rolname NOT IN (current_user,'pg_read_all_data')
                          AND pg_has_role(r.oid,'pg_read_all_data','member')
                    """).fetchone()[0]
                    associations = conn.execute("""
                        SELECT EXISTS(SELECT 1 FROM raw.magento_customer_order_item
                                      WHERE sales_order_item_item_id IS NOT NULL)
                    """).fetchone()[0]
                    counts = conn.execute("""
                        SELECT (SELECT COUNT(*) FROM core.dim_pessoa),
                               (SELECT COUNT(*) FROM core.pessoa_source_map),
                               (SELECT COUNT(*) FROM core.dim_pessoa
                                WHERE cpf_valido IS TRUE),
                               (SELECT COUNT(*) FROM (
                                   SELECT cpf_token_seguro FROM core.dim_pessoa
                                   WHERE cpf_token_seguro IS NOT NULL
                                   GROUP BY cpf_token_seguro HAVING COUNT(*)>1
                                ) duplicate_tokens),
                               (SELECT COUNT(*) FROM core.pessoa_source_map m
                                LEFT JOIN core.dim_pessoa d
                                  ON d.pessoa_key=m.pessoa_key
                                WHERE d.pessoa_key IS NULL),
                               (SELECT COUNT(*) FROM core.dim_pessoa WHERE cpf IS NOT NULL),
                               (SELECT COUNT(*) FROM core.dim_pessoa WHERE nome IS NOT NULL),
                               (SELECT COUNT(*) FROM core.dim_pessoa WHERE email IS NOT NULL),
                               (SELECT COUNT(*) FROM core.pessoa_source_map
                                WHERE papel_verificado IN ('COMPRADOR','AMBOS')),
                               (SELECT COUNT(*) FROM core.pessoa_source_map
                                WHERE papel_verificado IN ('PARTICIPANTE','AMBOS'))
                    """).fetchone()
                    print("CORE_PERSON_DIM "
                          f"installed={int(installed)} "
                          f"persons={counts[0]} source_maps={counts[1]} "
                          f"source_contract={int(contract)} ledger={int(ledger)} "
                          f"direct_readers={direct_readers} "
                          f"global_readers={global_readers} "
                          f"magento_associations_present={int(associations)} "
                          f"valid_cpf_persons={counts[2]} "
                          f"duplicate_tokens={counts[3]} "
                          f"orphan_maps={counts[4]} "
                          f"with_cpf={counts[5]} with_name={counts[6]} "
                          f"with_email={counts[7]} buyer_maps={counts[8]} "
                          f"participant_maps={counts[9]}")
                    for origin, role, count in conn.execute("""
                        SELECT origem,papel_verificado,COUNT(*)
                        FROM core.pessoa_source_map
                        GROUP BY origem,papel_verificado
                        ORDER BY origem,papel_verificado
                    """):
                        print(f"CORE_PERSON_ROLE origin={origin} role={role} count={count}")
                else:
                    if not conn.execute("SELECT pg_try_advisory_lock(%s)",
                                        (LOCK_ID,)).fetchone()[0]:
                        raise RuntimeError("Automação RAW/CORE em execução")
                    if not conn.execute("SELECT pg_try_advisory_lock(21001,1)").fetchone()[0]:
                        raise RuntimeError("Outra CORE em execução")
                    # Locks de sessão são liberados pelo fechamento da conexão.
                    if args.command == "migrate":
                        print("CORE_PERSON_DIM_MIGRATION "
                              f"applied={int(apply_migration(conn))}")
                    elif args.command == "rotate-key":
                        print("CORE_PERSON_KEY_ROTATED "
                              f"persons={rotate_key(conn, _hmac_key())}")
                    else:
                        since = args.since or datetime.now(
                            ZoneInfo("America/Sao_Paulo")).date()
                        result = backfill_since(conn, since, args.max_ids,
                                                args.until)
                        print("CORE_PERSON_DIM_BACKFILL "
                              f"since={since} until={args.until or 'open'} "
                              f"orders={result['orders']} "
                              f"inscriptions={result['inscriptions']} "
                              f"contacts={result['contacts']}")
        return 0
    except Exception as exc:
        # Falha por classe apenas: não imprimir parâmetros SQL nem PII.
        safe_reasons = {
            "Destino PostgreSQL inesperado",
            "CORE/schema_migration ausente",
            "Migração de contato divergente",
            "Migração de contato parcialmente aplicada",
            "dim_pessoa possui leitores adicionais; revisar grants",
            "Papéis com pg_read_all_data exigem revisão de acesso",
            "Contrato CORE/STAGING de pessoas incompatível",
            "Túnel SSH não iniciou",
            "Túnel SSH não respondeu",
            "Automação RAW/CORE em execução",
            "Outra CORE em execução",
            "Backfill de pedidos excede limite aprovado",
            "Backfill de inscrições excede limite aprovado",
            "Gate de sincronização PII fechado",
            "CPF válido requer chave HMAC provisionada",
            "Token de CPF existente divergente",
            "CPF de origem alterado; revisão de identidade necessária",
            "CPF já pertence a outra pessoa_key; revisão necessária",
            "Vínculo de CPF divergente; revisão necessária",
            "CPF validado ausente ou vínculo compartilhado; revisão necessária",
            "SCHEMA_DIVERGENTE: cadastro de origem ambíguo",
            "Chave HMAC diverge dos tokens gravados",
            "Rotação parcial da chave HMAC",
            "Chave HMAC de CPF não provisionada",
        }
        reason = str(exc) if type(exc) is RuntimeError and (
            str(exc) in safe_reasons or str(exc).startswith("cannot ")
        ) else type(exc).__name__
        print(f"CORE_PERSON_DIM_FAILED {reason}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

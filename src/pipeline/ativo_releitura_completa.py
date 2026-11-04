"""Releitura completa e mensal de pedidos e inscrições do Ativo.

As releituras por janela e por evento aberto não alcançam pedido antigo de evento já
encerrado. Roda dentro do ciclo, uma vez por mês civil, em cerca de 20 minutos, e só
grava o que mudou. O cursor fica em arquivo: se o notebook do túnel desligar no meio,
o ciclo seguinte continua de onde parou.
"""
import json
import os
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from psycopg import sql

from src.db import mysql, postgres
from src.pipeline.ativo_eventos_abertos import (CONTRACTS, LOCK_IDS, MAX_NEW_REMOVALS, TARGETS, log,
                                                mark_removed, restore_returned, write_changed)

SOURCE_TABLE = "sa_releitura_completa"
PIPELINE = "raw.ativo_releitura_completa"
TIMEZONE = ZoneInfo("America/Sao_Paulo")
# A releitura manual de 04/11/2026 vale por novembro.
FIRST_MONTH = "2026-12"
PAGE_SIZE = 10000
ENTITIES = ("pedido", "pedido_evento")


def month_of(moment):
    return moment.astimezone(TIMEZONE).strftime("%Y-%m")


def load_state(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_state(path, state):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    os.replace(temporary, path)


def is_due(connection, state_path):
    """Vence uma vez por mês civil; releitura interrompida continua, mesmo em outro mês."""
    if state_path.exists():
        return True
    now, previous = connection.execute(
        "SELECT clock_timestamp(),max(finished_at) FROM raw._etl_runs "
        "WHERE source_system='ativo' AND status='SUCCESS' AND source_table=%s", (SOURCE_TABLE,)
    ).fetchone()
    month = month_of(now)
    return month >= FIRST_MONTH and (previous is None or month_of(previous) != month)


def missing_ids(connection, entity, low, high, seen):
    """IDs na RAW, na faixa lida, que a origem não devolveu."""
    contract = CONTRACTS[entity]
    pk = sql.Identifier(contract.PK)
    return {row[0] for row in connection.execute(
        sql.SQL("SELECT {pk} FROM {table} WHERE {pk}>%s AND {pk}<=%s AND NOT ({pk}=ANY(%s))").format(
            pk=pk, table=sql.Identifier(*TARGETS[entity])), (low, high, seen)).fetchall()}


def reconcile_page(connection, reader, state, low, high, seen, batch_id, on_rows):
    """Só inscrição tem marca de removida; pedido que sumiu não muda nenhuma contagem."""
    if state["entity"] != "pedido_evento":
        return
    absent = missing_ids(connection, "pedido_evento", low, high, seen)
    if absent:
        removed = mark_removed(connection, reader, absent, batch_id, on_rows)
        state["mudaram"] += removed["movidas"]
        state["removidas"] += removed["novas"]
    restore_returned(connection, set(seen), batch_id, on_rows)
    connection.commit()


def assert_removals(state):
    # Um por execução: o estado salvo mantém a parada até alguém revisar.
    if state["removidas"] > MAX_NEW_REMOVALS:
        raise RuntimeError("Remoções acima do limite; revisão necessária")


def read_entity(connection, reader, state, save, batch_id, on_rows, assert_control):
    entity = state["entity"]
    if state["upper"] is None:
        state["upper"] = getattr(reader, f"ativo_{entity}_bounds")(count_total=False)[1] or 0
        save(state)
    page = getattr(reader, f"ativo_{entity}_page")
    while True:
        assert_control()
        assert_removals(state)
        rows = page(mode="FULL", batch_size=PAGE_SIZE, upper_id=state["upper"],
                    cursor=state["cursor"] or None, cutoff=None)
        if not rows:
            break
        ids = [row[0] for row in rows]
        state["mudaram"] += write_changed(connection, entity, rows, batch_id, on_rows)
        reconcile_page(connection, reader, state, state["cursor"], ids[-1], ids, batch_id, on_rows)
        state["cursor"], state["lidas"] = ids[-1], state["lidas"] + len(ids)
        save(state)
    # Acima do último ID devolvido e até o topo, a origem não tem mais nada.
    reconcile_page(connection, reader, state, state["cursor"], state["upper"], [], batch_id, on_rows)
    save(state)
    assert_removals(state)


def reread(connection, reader, state, save, batch_id, on_rows, assert_control):
    for entity in ENTITIES[ENTITIES.index(state["entity"]):]:
        if entity != state["entity"]:
            state.update(entity=entity, cursor=0, upper=None)
            save(state)
        read_entity(connection, reader, state, save, batch_id, on_rows, assert_control)
    return state


def new_state(now=None):
    return {"month": month_of(now or datetime.now(timezone.utc)), "entity": ENTITIES[0], "cursor": 0,
            "upper": None, "lidas": 0, "mudaram": 0, "removidas": 0}


def run(settings, state_path, on_rows, assert_control=lambda: None):
    batch_id = uuid4()
    state = load_state(state_path) or new_state()
    save = lambda current: save_state(state_path, current)
    with postgres.connect(settings) as connection:
        for lock in LOCK_IDS:
            if not connection.execute("SELECT pg_try_advisory_lock(%s)", (lock,)).fetchone()[0]:
                raise RuntimeError("Já existe carga Ativo em execução")
        connection.execute(
            "INSERT INTO raw._etl_runs (batch_id,pipeline_name,source_system,source_table,mode,status) "
            "VALUES (%s,%s,'ativo',%s,'RECONCILIATION','RUNNING')", (batch_id, PIPELINE, SOURCE_TABLE))
        connection.commit()
        try:
            with mysql.connect(settings, "ativo") as reader:
                database = settings.database("ativo").database
                for entity, contract in CONTRACTS.items():
                    contract.validate_schema(reader.columns(database, f"sa_{entity}"),
                                             reader.indexes(database, f"sa_{entity}"))
                reread(connection, reader, state, save, batch_id, on_rows, assert_control)
            connection.execute(
                "UPDATE raw._etl_runs SET status='SUCCESS',finished_at=clock_timestamp(),"
                "rows_extracted=%s,rows_loaded=%s WHERE batch_id=%s",
                (state["lidas"], state["mudaram"], batch_id))
            connection.commit()
            state_path.unlink()
        except BaseException as exc:
            connection.rollback()
            connection.execute(
                "UPDATE raw._etl_runs SET status='FAILED',finished_at=clock_timestamp(),error_message=%s "
                "WHERE batch_id=%s AND status='RUNNING'", (type(exc).__name__, batch_id))
            connection.commit()
            log("failed", table=SOURCE_TABLE, batch_id=batch_id, error=type(exc).__name__,
                entidade=state["entity"], cursor=state["cursor"])
            raise
        finally:
            if not connection.closed:
                for lock in LOCK_IDS:
                    connection.execute("SELECT pg_advisory_unlock(%s)", (lock,))
    log("success", table=SOURCE_TABLE, batch_id=batch_id, lidas=state["lidas"],
        mudaram=state["mudaram"], removidas=state["removidas"])
    return state

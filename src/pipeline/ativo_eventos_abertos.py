"""Relê pedidos e inscrições de eventos abertos e marca o que sumiu da origem.

A reconciliação por janela olha só `dt_pedido` recente: estorno ou cancelamento
em pedido antigo de evento que ainda vai acontecer nunca chegava à RAW. Aqui a
seleção é pelo evento. Só o que mudou é gravado e vai ao diário da CORE.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4

from psycopg import sql

from src.db import mysql, postgres
from src.sources.ativo import pedido, pedido_evento

SOURCE_TABLE = "sa_pedido_evento_abertos"
PIPELINE = "raw.ativo_eventos_abertos"
PAST_DAYS = 30
BATCH_SIZE = 5000
ID_CHUNK = 1000
# Acima disso é mais provável problema na leitura do que remoção real.
MAX_NEW_REMOVALS = 5000
LOCK_IDS = (7248319301, 7248319302)
TARGETS = {"pedido": ("raw", "ativo_pedido"), "pedido_evento": ("raw", "ativo_pedido_evento")}
CONTRACTS = {"pedido": pedido, "pedido_evento": pedido_evento}


def log(event, **fields):
    print(json.dumps({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                      "source": "ativo", "table": SOURCE_TABLE, **fields}, default=str), flush=True)


def chunks(values, size=ID_CHUNK):
    values = sorted(values)
    for start in range(0, len(values), size):
        yield values[start:start + size]


def open_events(connection):
    """dt_evento é TEXT ISO com datas zero na origem: a comparação textual as descarta."""
    return [row[0] for row in connection.execute(
        "SELECT id_evento FROM raw.ativo_evento "
        "WHERE dt_evento >= to_char(current_date - %s::int, 'YYYY-MM-DD') ORDER BY id_evento",
        (PAST_DAYS,)).fetchall()]


def write_changed(connection, entity, rows, batch_id, on_rows):
    """UPSERT que só toca linhas diferentes; registra no diário antes do COMMIT."""
    if not rows:
        return 0
    contract, target = CONTRACTS[entity], TARGETS[entity]
    columns = (*contract.COLUMNS, "_source", "_extracted_at", "_batch_id")
    names = sql.SQL(", ").join(map(sql.Identifier, columns))
    pk = sql.Identifier(contract.PK)
    connection.execute(sql.SQL("CREATE TEMP TABLE etl_abertos (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP")
                       .format(sql.Identifier(*target)))
    now = datetime.now(timezone.utc)
    with connection.cursor() as cursor:
        with cursor.copy(sql.SQL("COPY pg_temp.etl_abertos ({}) FROM STDIN").format(names)) as copy:
            for row in rows:
                copy.write_row((*row, "ativo", now, batch_id))
        assignments = sql.SQL(", ").join(sql.SQL("{0}=EXCLUDED.{0}").format(sql.Identifier(c))
                                         for c in columns if c != contract.PK)
        old = sql.SQL(", ").join(sql.SQL("t.{}").format(sql.Identifier(c)) for c in contract.COLUMNS)
        new = sql.SQL(", ").join(sql.SQL("EXCLUDED.{}").format(sql.Identifier(c)) for c in contract.COLUMNS)
        cursor.execute(sql.SQL(
            "INSERT INTO {target} AS t ({names}) SELECT {names} FROM pg_temp.etl_abertos "
            "ON CONFLICT ({pk}) DO UPDATE SET {assignments} WHERE ({old}) IS DISTINCT FROM ({new}) "
            "RETURNING t.{pk}"
        ).format(target=sql.Identifier(*target), names=names, pk=pk,
                 assignments=assignments, old=old, new=new))
        changed = {row[0] for row in cursor.fetchall()}
    if changed and on_rows is not None:
        on_rows("ativo", entity, batch_id, [row for row in rows if row[0] in changed], contract.COLUMNS)
    connection.commit()
    return len(changed)


def raw_rows(connection, ids):
    contract = CONTRACTS["pedido_evento"]
    rows = []
    for part in chunks(ids):
        rows += connection.execute(sql.SQL("SELECT {} FROM raw.ativo_pedido_evento WHERE id_pedido_evento=ANY(%s)")
                                   .format(sql.SQL(", ").join(map(sql.Identifier, contract.COLUMNS))),
                                   (part,)).fetchall()
    return rows


def mark_removed(connection, reader, candidates, batch_id, on_rows):
    """Confirma por PK na origem: inscrição movida de evento existe e não é remoção."""
    found = []
    for part in chunks(candidates):
        found += reader.ativo_pedido_evento_by_ids(ids=part)
    changed = write_changed(connection, "pedido_evento", found, batch_id, on_rows)
    existing = {row[0] for row in found}
    absent = set(candidates) - existing
    known = {row[0] for row in connection.execute(
        "SELECT inscricao_id_origem FROM core.inscricao_removida_origem WHERE origem='ativo'").fetchall()}
    new = absent - known
    if len(new) > MAX_NEW_REMOVALS:
        raise RuntimeError("Remoções acima do limite; revisão necessária")
    for part in chunks(new):
        connection.execute(
            "INSERT INTO core.inscricao_removida_origem (origem,inscricao_id_origem,batch_id) "
            "SELECT 'ativo',id,%s FROM unnest(%s::bigint[]) id ON CONFLICT DO NOTHING", (batch_id, part))
    if new and on_rows is not None:
        on_rows("ativo", "pedido_evento", batch_id, raw_rows(connection, new),
                CONTRACTS["pedido_evento"].COLUMNS)
    connection.commit()
    return {"novas": len(new), "movidas": changed}


def restore_returned(connection, seen, batch_id, on_rows):
    """Inscrição que voltou à origem deixa de estar marcada e volta a ser derivada."""
    known = {row[0] for row in connection.execute(
        "SELECT inscricao_id_origem FROM core.inscricao_removida_origem WHERE origem='ativo'").fetchall()}
    back = known & seen
    for part in chunks(back):
        connection.execute("DELETE FROM core.inscricao_removida_origem "
                           "WHERE origem='ativo' AND inscricao_id_origem=ANY(%s::bigint[])", (part,))
    if back and on_rows is not None:
        on_rows("ativo", "pedido_evento", batch_id, raw_rows(connection, back),
                CONTRACTS["pedido_evento"].COLUMNS)
    connection.commit()
    return len(back)


def reread(connection, reader, batch_id, on_rows):
    events = open_events(connection)
    connection.commit()
    totals = {"eventos": len(events), "inscricoes": 0, "inscricoes_mudaram": 0,
              "pedidos": 0, "pedidos_mudaram": 0}
    seen = set()
    for event_id in events:
        cursor = None
        while True:
            rows = reader.ativo_pedido_evento_by_event(event_id=event_id, batch_size=BATCH_SIZE, cursor=cursor)
            if not rows:
                break
            cursor = rows[-1][0]
            seen.update(row[0] for row in rows)
            totals["inscricoes"] += len(rows)
            totals["inscricoes_mudaram"] += write_changed(connection, "pedido_evento", rows, batch_id, on_rows)
            orders = {row[CONTRACTS["pedido_evento"].COLUMNS.index("id_pedido")] for row in rows}
            for part in chunks(orders):
                order_rows = reader.ativo_pedido_by_ids(ids=part)
                totals["pedidos"] += len(order_rows)
                totals["pedidos_mudaram"] += write_changed(connection, "pedido", order_rows, batch_id, on_rows)
    # RAW sem índice em id_evento: uma varredura por execução, com folga no tempo.
    connection.execute("SET LOCAL statement_timeout=600000")
    in_raw = {row[0] for row in connection.execute(
        "SELECT id_pedido_evento FROM raw.ativo_pedido_evento WHERE id_evento=ANY(%s::int[])", (events,)).fetchall()}
    connection.commit()
    removed = mark_removed(connection, reader, in_raw - seen, batch_id, on_rows)
    totals["removidas_novas"] = removed["novas"]
    totals["movidas"] = removed["movidas"]
    totals["voltaram"] = restore_returned(connection, seen, batch_id, on_rows)
    return totals


def run(settings, on_rows=None):
    batch_id = uuid4()
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
                totals = reread(connection, reader, batch_id, on_rows)
            connection.execute(
                "UPDATE raw._etl_runs SET status='SUCCESS',finished_at=clock_timestamp(),"
                "rows_extracted=%s,rows_loaded=%s WHERE batch_id=%s",
                (totals["inscricoes"] + totals["pedidos"],
                 totals["inscricoes_mudaram"] + totals["pedidos_mudaram"], batch_id))
            connection.commit()
        except BaseException as exc:
            connection.rollback()
            connection.execute(
                "UPDATE raw._etl_runs SET status='FAILED',finished_at=clock_timestamp(),error_message=%s "
                "WHERE batch_id=%s AND status='RUNNING'", (type(exc).__name__, batch_id))
            connection.commit()
            log("failed", batch_id=batch_id, error=type(exc).__name__)
            raise
        finally:
            if not connection.closed:
                for lock in LOCK_IDS:
                    connection.execute("SELECT pg_advisory_unlock(%s)", (lock,))
    log("success", batch_id=batch_id, **totals)
    return totals

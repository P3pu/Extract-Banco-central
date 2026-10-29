"""Executor Windows: MySQL -> RAW -> CORE, por túnel SSH restrito.

Não contém FULL, DDL, senhas, comandos remotos nem abertura de indicadores.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import psycopg

from src.automation.change_journal import ChangeJournal
from src.automation.core_refresh import refresh
from src.config.settings import Settings


LOCK_ID = 7248319999
LOCAL_PORT = 15943
RECONCILIATION_DAYS = 30
RECONCILIATION_INTERVAL = timedelta(days=15)
CONTROL_HEARTBEAT_SECONDS = 15
ENTITIES = (("ativo", "pedido"), ("ativo", "pedido_evento"),
            ("magento", "sales_order"), ("magento", "sales_order_item"))
# Cadastros e referenciais: sem eles, pedidos novos apontam para eventos,
# usuários, produtos e clientes ausentes da RAW.
AUX_INTERVAL = timedelta(hours=24)
AUX_COMMANDS = (
    ("snapshot", "ativo", (None,)),
    ("incremental", "ativo", ("usuario", "usuario_balcao", "pedido_pagamento",
                              "transacao", "pedido_produto", "pedido_endereco",
                              "cupom_desconto_item")),
    ("incremental", "magento", ("product", "product_varchar", "product_int",
                                "product_datetime", "product_link", "customer",
                                "customer_address", "customer_order_item",
                                "company", "company_user", "salesrule",
                                "salesrule_label")),
    ("snapshot", "magento", ("eav_attribute", "option_value")),
)
AUX_RECONCILE = ("usuario", "usuario_balcao", "pedido_pagamento", "transacao",
                 "pedido_endereco")
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def windows_execution_state(flags):
    import ctypes
    action = ctypes.WinDLL("kernel32", use_last_error=True).SetThreadExecutionState
    action.argtypes = [ctypes.c_uint]
    action.restype = ctypes.c_uint
    if action(flags) == 0:
        raise RuntimeError("Não foi possível impedir suspensão durante a carga")


@contextmanager
def prevent_idle_sleep():
    """Evita suspensão por ociosidade enquanto houver transação e túnel ativos."""
    if os.name != "nt":
        yield
        return
    windows_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    try:
        yield
    finally:
        windows_execution_state(ES_CONTINUOUS)


def direct_postgres() -> bool:
    """Servidor: o PostgreSQL está no próprio host; não há túnel SSH."""
    return os.environ.get("BCD_DIRECT_POSTGRES") == "1"


def journal_path() -> Path:
    state = os.environ.get("BCD_STATE_DIR")
    if state:
        return Path(state) / "pending.sqlite"
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("LOCALAPPDATA ausente")
    return Path(base) / "BancoCentralDados" / "pending.sqlite"


@contextmanager
def postgres_tunnel(settings):
    key = Path.home() / ".ssh" / "bcd_automation_ed25519"
    if key.is_symlink() or not key.is_file():
        raise RuntimeError("Chave SSH dedicada ausente")
    # `settings` já aponta ao loopback/LOCAL_PORT. O destino do -L deve vir
    # da configuração original, antes da substituição feita por local_settings.
    original_pg = Settings.load().database("postgres")
    host = os.environ.get("BCD_SSH_HOST") or original_pg.host
    remote_port = original_pg.port
    args = ["ssh", "-N", "-i", str(key), "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=2", "-o", "ConnectTimeout=10",
            "-L", f"127.0.0.1:{LOCAL_PORT}:127.0.0.1:{remote_port}",
            f"bcd_tunnel@{host}"]
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Túnel SSH não iniciou")
            try:
                with socket.create_connection(("127.0.0.1", LOCAL_PORT), timeout=1):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Túnel SSH não respondeu")
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@contextmanager
def postgres_access(settings):
    if direct_postgres():
        yield
        return
    with postgres_tunnel(settings):
        yield


def local_settings() -> Settings:
    original = Settings.load()
    # Direto: loopback do servidor na porta publicada; senão, a ponta local do túnel.
    port = original.database("postgres").port if direct_postgres() else LOCAL_PORT
    env = {**original.env, "POSTGRES_HOST": "127.0.0.1",
           "POSTGRES_PORT": str(port), "POSTGRES_SSLMODE": "disable",
           "RECONCILIATION_DAYS": str(RECONCILIATION_DAYS)}
    return Settings.load(env)


@contextmanager
def control_connection(settings):
    pg = settings.database("postgres")
    with psycopg.connect(host=pg.host, port=pg.port, dbname=pg.database,
                         user=pg.user, password=pg.password, sslmode="disable",
                         connect_timeout=10, autocommit=True,
                         application_name="bcd-local-automation",
                         options=("-c statement_timeout=60000 -c lock_timeout=5000 "
                                  "-c idle_session_timeout=120000")) as conn:
        if conn.execute("SELECT current_database()").fetchone()[0] != "Atendimento":
            raise RuntimeError("Destino PostgreSQL inesperado")
        if not conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
            raise RuntimeError("Outra execução automática está ativa")
        stop = threading.Event()
        failed = threading.Event()

        def heartbeat():
            while not stop.wait(CONTROL_HEARTBEAT_SECONDS):
                try:
                    conn.execute("SELECT 1")
                except psycopg.Error:
                    failed.set()
                    return

        worker = threading.Thread(target=heartbeat, name="bcd-control-heartbeat",
                                  daemon=True)
        worker.start()

        def assert_control():
            if failed.is_set() or conn.closed:
                raise RuntimeError("Lock de controle da automação perdido")

        try:
            yield conn, assert_control
            assert_control()
        finally:
            stop.set()
            worker.join(timeout=5)
            if worker.is_alive():
                raise RuntimeError("Heartbeat de controle não encerrou")
            if not conn.closed:
                try:
                    released = conn.execute(
                        "SELECT pg_advisory_unlock(%s)", (LOCK_ID,)
                    ).fetchone()[0]
                    if not released:
                        raise RuntimeError("Lock de controle não estava ativo")
                except psycopg.Error as exc:
                    raise RuntimeError("Não foi possível liberar lock de controle") from exc


def due_reconciliations(conn):
    now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
    rows = conn.execute(
        "SELECT source_table,max(finished_at) FROM raw._etl_runs "
        "WHERE source_system='ativo' AND mode='RECONCILIATION' "
        "AND status='SUCCESS' AND source_table IN ('sa_pedido','sa_pedido_evento') "
        "GROUP BY source_table"
    ).fetchall()
    last = dict(rows)
    due = []
    for entity in ("pedido", "pedido_evento"):
        previous = last.get(f"sa_{entity}")
        if previous is not None and previous > now:
            raise RuntimeError("Relógio da reconciliação inconsistente")
        if previous is None or now - previous >= RECONCILIATION_INTERVAL:
            due.append(entity)
    return due


def source_failed(failed, origin, step, exc):
    """Uma origem indisponível não impede as demais; o watermark dela não avança."""
    failed.add(origin)
    print(f"AUTOMATION_SOURCE_FAILED {origin} {step} {type(exc).__name__}",
          file=sys.stderr, flush=True)


def run_raw(settings, journal, due, assert_control=lambda: None):
    """Retorna as origens que falharam; as etapas seguintes dela são puladas."""
    from src.pipeline import ativo_pedido, sales_order
    failed = set()
    steps = [(origin, "INCREMENTAL", entity) for origin, entity in ENTITIES]
    steps += [("ativo", "RECONCILIATION", entity) for entity in due]
    for origin, mode, entity in steps:
        assert_control()
        if origin in failed:
            continue
        pipeline = ativo_pedido if origin == "ativo" else sales_order
        kwargs = {"days": RECONCILIATION_DAYS} if mode == "RECONCILIATION" else {}
        try:
            pipeline.run(settings, mode, batch_size=1000, entity=entity,
                         on_rows=journal.record_rows, **kwargs)
        except Exception as exc:
            source_failed(failed, origin, entity, exc)
    return failed


def aux_due(conn):
    """(cadastros vencidos, reconciliação de cadastros vencida)."""
    now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
    snapshot, reconciled = conn.execute(
        "SELECT max(finished_at) FILTER (WHERE source_table='sa_evento' "
        "AND mode='SNAPSHOT'), max(finished_at) FILTER (WHERE "
        "source_table='sa_usuario' AND mode='RECONCILIATION') "
        "FROM raw._etl_runs WHERE source_system='ativo' AND status='SUCCESS'"
    ).fetchone()
    for previous in (snapshot, reconciled):
        if previous is not None and previous > now:
            raise RuntimeError("Relógio dos cadastros inconsistente")
    return (snapshot is None or now - snapshot >= AUX_INTERVAL,
            reconciled is None or now - reconciled >= RECONCILIATION_INTERVAL)


def run_aux(settings, reconcile_days=None, assert_control=lambda: None):
    """Executa a CLI RAW existente pelo túnel; sem FULL."""
    from src import main as cli
    pg = settings.database("postgres")
    os.environ.update(POSTGRES_HOST=pg.host, POSTGRES_PORT=str(pg.port),
                      POSTGRES_SSLMODE="disable")
    commands = [[command, "--source", source] + (["--entity", entity] if entity else [])
                for command, source, entities in AUX_COMMANDS for entity in entities]
    if reconcile_days is not None:
        commands += [["reconcile", "--source", "ativo", "--entity", entity,
                      "--days", str(reconcile_days)] for entity in AUX_RECONCILE]
    failed = set()
    for argv in commands:
        assert_control()
        origin = argv[2]
        if origin in failed:
            continue
        if cli.main(argv) != 0:
            source_failed(failed, origin, argv[-1], RuntimeError())
    return len(commands), failed


def run_core(settings, journal, assert_control=lambda: None):
    pending = journal.snapshot()
    if not pending:
        return {"orders": 0, "inscriptions": 0}
    from src.core import runner
    pg = settings.database("postgres")
    os.environ.update(CORE_PG_HOST=pg.host, CORE_PG_PORT=str(pg.port),
                      CORE_PG_DATABASE=pg.database, CORE_PG_USER=pg.user,
                      CORE_PG_PASSWORD=pg.password, CORE_PG_SSLMODE="disable",
                      CORE_PRODUCTION_APPROVAL="CORE_V1_APPROVED")
    with runner.connect() as conn:
        runner.validate_destination(conn, True)
        result = refresh(conn, pending, assert_control=assert_control)
    assert_control()
    journal.clear()
    return result


def bootstrap(conn, journal, since):
    """Uma única leitura histórica limitada por data de extração RAW."""
    sources = (
        ("magento", "sales_order", "raw.magento_sales_order", "entity_id", None, None),
        ("magento", "sales_order_item", "raw.magento_sales_order_item",
         "item_id", "order_id", "parent_item_id"),
        ("ativo", "pedido", "raw.ativo_pedido", "id_pedido", None, None),
        ("ativo", "pedido_evento", "raw.ativo_pedido_evento",
         "id_pedido_evento", "id_pedido", None),
    )
    for origin, entity, table, id_col, order_col, parent_col in sources:
        selected = [id_col] + ([order_col] if order_col else []) + ([parent_col] if parent_col else [])
        query = f"SELECT {','.join(selected)} FROM {table} WHERE _extracted_at >= %s"
        with conn.cursor() as cursor:
            cursor.execute(query, (since,))
            while rows := cursor.fetchmany(1000):
                journal.record_rows(origin, entity, None, rows, selected)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Automação local RAW -> CORE")
    parser.add_argument("command", choices=("check", "lock-status", "plan-core", "audit-core", "run-once", "core-only", "bootstrap"))
    parser.add_argument("--since", type=datetime.fromisoformat)
    parser.add_argument("--min-id", type=int)
    parser.add_argument("--max-id", type=int)
    args = parser.parse_args(argv)
    if args.command == "bootstrap" and args.since is None:
        parser.error("bootstrap requer --since com fuso horário")
    if args.since is not None and args.since.tzinfo is None:
        parser.error("--since requer fuso horário")
    try:
        if args.command in {"run-once", "core-only"} and os.environ.get(
            "BCD_AUTOMATION_ENABLE"
        ) != "approved":
            raise RuntimeError("Automação de escrita desabilitada")
        settings = Settings.load()
        success_message = None
        exit_code = 0
        with prevent_idle_sleep(), postgres_access(settings):
            settings = local_settings()
            if args.command == "lock-status":
                pg = settings.database("postgres")
                with psycopg.connect(host=pg.host, port=pg.port, dbname=pg.database,
                                     user=pg.user, password=pg.password,
                                     sslmode="disable", connect_timeout=10) as diagnostic:
                    with diagnostic.transaction():
                        diagnostic.execute("SET TRANSACTION READ ONLY")
                        rows = diagnostic.execute(
                            "SELECT a.pid,a.application_name,a.state,"
                            "EXTRACT(EPOCH FROM clock_timestamp()-a.state_change)::integer "
                            "FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid "
                            "WHERE l.locktype='advisory' AND l.granted "
                            "AND l.classid::bigint=%s AND l.objid::bigint=%s",
                            (LOCK_ID >> 32, LOCK_ID & 0xffffffff),
                        ).fetchall()
                        print(f"CONTROL_LOCK_HOLDERS {rows}", flush=True)
                        timeout = diagnostic.execute("SHOW idle_session_timeout").fetchone()[0]
                        print(f"CONTROL_IDLE_TIMEOUT {timeout}", flush=True)
                return 0
            with control_connection(settings) as (conn, assert_control):
                if args.command == "check":
                    from src.db.mysql import connect as mysql_connect
                    for origin in ("ativo", "magento"):
                        with mysql_connect(settings, origin) as reader:
                            if reader.ping() != settings.database(origin).database:
                                raise RuntimeError("Origem MySQL inesperada")
                    print("AUTOMATION_CHECK_OK", flush=True)
                    return 0
                journal = ChangeJournal(journal_path())
                try:
                    if args.command == "audit-core":
                        with conn.transaction():
                            conn.execute("SET TRANSACTION READ ONLY")
                            rows = conn.execute(
                                "SELECT escopo,limite_inferior,limite_superior,status,erro_codigo "
                                "FROM core.core_etl_execucao "
                                "ORDER BY iniciada_em DESC LIMIT 8"
                            ).fetchall()
                            for row in rows:
                                print("CORE_AUDIT", *row, flush=True)
                            gate_count = conn.execute(
                                "SELECT count(*) FROM core.fato_inscricao_indicadores_validos"
                            ).fetchone()[0]
                            stale_count = conn.execute(
                                "SELECT count(*) FROM core.core_etl_execucao "
                                "WHERE status='RUNNING' "
                                "AND iniciada_em<clock_timestamp()-interval '5 minutes'"
                            ).fetchone()[0]
                            print(f"CORE_AUDIT_GATE rows={gate_count} "
                                  f"stale_running={stale_count}", flush=True)
                            if stale_count:
                                stale = conn.execute(
                                    "SELECT escopo,limite_inferior,limite_superior,iniciada_em "
                                    "FROM core.core_etl_execucao WHERE status='RUNNING' "
                                    "AND iniciada_em<clock_timestamp()-interval '5 minutes' "
                                    "ORDER BY iniciada_em DESC LIMIT 10"
                                ).fetchall()
                                for row in stale:
                                    print("CORE_AUDIT_STALE", *row, flush=True)
                            if args.min_id is not None and args.max_id is not None:
                                if args.min_id < 0 or args.max_id < args.min_id or args.max_id - args.min_id >= 100000:
                                    raise ValueError("Faixa diagnóstica inválida")
                                n = conn.execute(
                                    "SELECT count(*) FROM core.fato_inscricao "
                                    "WHERE origem='magento' AND inscricao_id_origem BETWEEN %s AND %s",
                                    (args.min_id, args.max_id),
                                ).fetchone()[0]
                                print(f"CORE_AUDIT_RANGE inscriptions_magento={n}", flush=True)
                    elif args.command == "plan-core":
                        from src.automation.core_refresh import affected_ids
                        with conn.transaction():
                            conn.execute("SET TRANSACTION READ ONLY")
                            pending = journal.snapshot()
                            orders, inscriptions = affected_ids(conn, pending)
                            for label, groups in (("orders", orders), ("inscriptions", inscriptions)):
                                for origin in ("ativo", "magento"):
                                    values = groups[origin]
                                    print(f"CORE_PLAN {label} {origin} ids={len(values)} "
                                          f"buckets_10k={len({value // 10000 for value in values})} "
                                          f"buckets_100k={len({value // 100000 for value in values})}", flush=True)
                                    if label == "inscriptions" and values:
                                        from collections import Counter
                                        heavy = Counter(value // 100000 for value in values)
                                        for bucket, count in heavy.most_common(3):
                                            print(f"CORE_PLAN_HEAVY {origin} "
                                                  f"range={bucket * 100000}-{bucket * 100000 + 99999} "
                                                  f"ids={count}", flush=True)
                            from src.automation.core_refresh import target_ranges
                            all_ids = set().union(*inscriptions.values())
                            print(f"CORE_PLAN_TARGET_BATCHES {len(target_ranges(all_ids))}", flush=True)
                    elif args.command == "bootstrap":
                        bootstrap(conn, journal, args.since.astimezone(timezone.utc))
                        success_message = f"AUTOMATION_BOOTSTRAP_OK pending={len(journal.snapshot())}"
                    elif args.command == "core-only":
                        result = run_core(settings, journal, assert_control)
                        success_message = f"AUTOMATION_CORE_OK {result}"
                    else:
                        aux, aux_reconcile = aux_due(conn)
                        aux_steps, failed = run_aux(
                            settings,
                            RECONCILIATION_DAYS if aux_reconcile else None,
                            assert_control) if aux else (0, set())
                        due = due_reconciliations(conn)
                        failed |= run_raw(settings, journal, due, assert_control)
                        # A CORE processa o que as origens disponíveis carregaram.
                        result = run_core(settings, journal, assert_control)
                        status = ("AUTOMATION_CYCLE_PARTIAL failed=" + ",".join(sorted(failed))
                                  if failed else "AUTOMATION_CYCLE_OK")
                        success_message = (f"{status} aux_steps={aux_steps} "
                                           f"due_reconciliation={len(due)} core={result}")
                        if failed:
                            exit_code = 2
                finally:
                    journal.close()
        if success_message:
            print(success_message, flush=True)
        return exit_code
    except Exception as exc:
        # Exceções de drivers podem conter SQL, senhas ou PII: só a classe.
        print(f"AUTOMATION_FAILED {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Rederivação supervisionada de inscrições invalidadas pelo antigo 022.

Segura o lock de controle da automação durante toda a carga: os ciclos
horários recusam rodar em paralelo e preservam o diário. Usa o mesmo túnel
SSH restrito; não contém FULL, DDL nem senhas.
"""

import argparse
from datetime import datetime
import os
import sys
import time
from zoneinfo import ZoneInfo

from src.automation import local_raw_core
from src.config.settings import Settings
from src.core import verified_bulk


LOCK_WAIT_SECONDS = 45 * 60
LOCK_RETRY_SECONDS = 60
# Cadastros parados desde 28/09: a janela cobre o mês sem atualização.
AUX_RECONCILE_DAYS = 31

# Faixas com derivado_de_dependencias_hash NULL medidas em 28/10/2026.
# Ativo primeiro: faixa pequena, confere o caminho antes da carga longa.
RANGES = (
    ("ativo", 19_400_000, 19_619_999, 20_000, True),
    # Desde 0: inclui inscrições dos eventos unificados em 28/10 abaixo de 380 mil.
    ("magento", 0, 7_309_999, 10_000, False),
)


def stuck_count(conn):
    return conn.execute(
        "SELECT count(*) FROM core.fato_inscricao "
        "WHERE derivado_de_dependencias_hash IS NULL"
    ).fetchone()[0]


def run(settings, assert_control, conn, as_of):
    steps = local_raw_core.run_aux(settings, AUX_RECONCILE_DAYS, assert_control)
    print(f"RECOVERY_AUX_OK steps={steps}", flush=True)
    pg = settings.database("postgres")
    os.environ.update(CORE_PG_HOST=pg.host, CORE_PG_PORT=str(pg.port),
                      CORE_PG_DATABASE=pg.database, CORE_PG_USER=pg.user,
                      CORE_PG_PASSWORD=pg.password, CORE_PG_SSLMODE="disable",
                      CORE_PRODUCTION_APPROVAL="CORE_V1_APPROVED")
    print(f"RECOVERY_STUCK_BEFORE {stuck_count(conn)}", flush=True)
    for label, low, high, chunk, ativo_only in RANGES:
        assert_control()
        print(f"RECOVERY_RANGE_START {label} {low} {high}", flush=True)
        argv = ["--min-id", str(low), "--max-id", str(high),
                "--chunk-size", str(chunk), "--as-of", as_of.isoformat(),
                # UPDATE de ~1,5 mi linhas gera versões mortas; 31 GB livres.
                "--max-db-growth-gib", "4",
                "--approve-production"]
        if ativo_only:
            argv.append("--ativo-only")
        if verified_bulk.main(argv) != 0:
            raise RuntimeError("Carga CORE de recuperação falhou")
        print(f"RECOVERY_RANGE_OK {label}", flush=True)
    remaining = stuck_count(conn)
    print(f"RECOVERY_STUCK_AFTER {remaining}", flush=True)
    return remaining


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        if os.environ.get("BCD_AUTOMATION_ENABLE") != "approved":
            raise RuntimeError("Automação de escrita desabilitada")
        as_of = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        with local_raw_core.prevent_idle_sleep(), \
                local_raw_core.postgres_access(Settings.load()):
            settings = local_raw_core.local_settings()
            # O ciclo horário dispara no mesmo minuto; aguarda o lock dele.
            deadline = time.monotonic() + LOCK_WAIT_SECONDS
            while True:
                try:
                    control = local_raw_core.control_connection(settings)
                    conn, assert_control = control.__enter__()
                    break
                except RuntimeError as exc:
                    if ("Outra execução" not in str(exc)
                            or time.monotonic() > deadline):
                        raise
                    print("RECOVERY_WAITING_LOCK", flush=True)
                    time.sleep(LOCK_RETRY_SECONDS)
            try:
                run(settings, assert_control, conn, as_of)
            except BaseException:
                if not control.__exit__(*sys.exc_info()):
                    raise
            else:
                control.__exit__(None, None, None)
        print("RECOVERY_OK", flush=True)
        return 0
    except Exception as exc:
        # Exceções de drivers podem conter SQL, senhas ou PII: só a classe.
        print(f"RECOVERY_FAILED {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

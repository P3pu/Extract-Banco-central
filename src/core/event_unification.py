"""Unificação validada de eventos Magento a eventos Ativo de mesmo SKU.

Cada linha aprovada faz o evento Magento apontar para o `evento_key` do
evento Ativo em `core.evento_source_map` (`MANUAL_VALIDADO`), que a carga
de eventos nunca sobrescreve. As inscrições passam a usar o novo vínculo na
próxima derivação da faixa (030 compara `evento_key` no hash de conteúdo).

Usa o túnel e o lock de controle da automação local; não contém DDL.
"""

import argparse
import csv
from pathlib import Path
import sys

from src.automation import local_raw_core
from src.config.settings import Settings


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILE = ROOT / "sql/core/v1/data/evento_unificacao_20261028.csv"
REVIEWER = "regra SKU+data aprovada em 28/10/2026"


def load_decisions(path):
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    decisions = []
    seen = set()
    for row in rows:
        magento_id, ativo_id = int(row["magento_evento_id"]), int(row["ativo_evento_id"])
        sku = (row["sku"] or "").strip()
        if not sku or magento_id < 0 or ativo_id < 0:
            raise ValueError("Linha de unificação inválida")
        if magento_id in seen:
            raise ValueError("Evento Magento repetido no arquivo")
        seen.add(magento_id)
        decisions.append((sku, magento_id, ativo_id))
    if not decisions:
        raise ValueError("Arquivo de unificação vazio")
    return decisions


def stage(conn, decisions):
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS core_evento_unificacao "
                 "(sku TEXT NOT NULL, magento_id BIGINT PRIMARY KEY, "
                 "ativo_id BIGINT NOT NULL) ON COMMIT DROP")
    with conn.cursor() as cursor:
        cursor.executemany("INSERT INTO core_evento_unificacao VALUES (%s,%s,%s)",
                           decisions)


def validate(conn):
    """Recusa o lote inteiro se qualquer par divergir da CORE."""
    problems = conn.execute("""
        SELECT u.magento_id,
               CASE WHEN m.evento_key IS NULL THEN 'MAGENTO_AUSENTE'
                    WHEN a.evento_key IS NULL THEN 'ATIVO_AUSENTE'
                    WHEN a.flag_evento_teste THEN 'ATIVO_TESTE'
                    WHEN btrim(m.sku_referencia) IS DISTINCT FROM u.sku
                      OR btrim(a.sku_referencia) IS DISTINCT FROM u.sku THEN 'SKU_DIVERGENTE'
                    WHEN s.criterio_vinculo IS DISTINCT FROM 'ORIGEM'
                     AND s.evento_key IS DISTINCT FROM a.evento_key THEN 'VINCULO_MANUAL_DIFERENTE'
               END problema
        FROM core_evento_unificacao u
        LEFT JOIN core.dim_evento m ON m.seed_origem='magento' AND m.seed_evento_id=u.magento_id
        LEFT JOIN core.dim_evento a ON a.seed_origem='ativo' AND a.seed_evento_id=u.ativo_id
        LEFT JOIN core.evento_source_map s ON s.origem='magento' AND s.evento_id_origem=u.magento_id
    """).fetchall()
    bad = [(magento_id, problem) for magento_id, problem in problems if problem]
    if bad:
        for magento_id, problem in bad[:20]:
            print(f"EVENT_UNIFY_INVALID magento_evento_id={magento_id} {problem}", flush=True)
        raise RuntimeError(f"{len(bad)} vínculo(s) inválido(s); nada foi gravado")


def impact(conn):
    return conn.execute("""
        SELECT count(DISTINCT u.magento_id), count(f.inscricao_key),
               min(f.inscricao_id_origem), max(f.inscricao_id_origem)
        FROM core_evento_unificacao u
        LEFT JOIN core.fato_inscricao f
          ON f.origem='magento' AND f.evento_id_origem=u.magento_id
    """).fetchone()


def apply(conn):
    mapped = conn.execute("""
        UPDATE core.evento_source_map s
        SET evento_key=a.evento_key, criterio_vinculo='MANUAL_VALIDADO',
            revisado_por=%s, revisado_em=clock_timestamp()
        FROM core_evento_unificacao u
        JOIN core.dim_evento a ON a.seed_origem='ativo' AND a.seed_evento_id=u.ativo_id
        WHERE s.origem='magento' AND s.evento_id_origem=u.magento_id
          AND (s.criterio_vinculo, s.evento_key)
              IS DISTINCT FROM ('MANUAL_VALIDADO', a.evento_key)
    """, (REVIEWER,)).rowcount
    marked = conn.execute("""
        UPDATE core.dim_evento d SET status_mapeamento='UNIFICADO_VALIDADO',
            data_atualizacao_core=clock_timestamp()
        FROM core_evento_unificacao u
        WHERE ((d.seed_origem='magento' AND d.seed_evento_id=u.magento_id)
            OR (d.seed_origem='ativo' AND d.seed_evento_id=u.ativo_id))
          AND d.status_mapeamento<>'UNIFICADO_VALIDADO'
    """).rowcount
    return mapped, marked


def revert(conn):
    """Volta cada evento Magento do arquivo a apontar para si mesmo."""
    mapped = conn.execute("""
        UPDATE core.evento_source_map s
        SET evento_key=m.evento_key, criterio_vinculo='ORIGEM',
            revisado_por=NULL, revisado_em=NULL
        FROM core_evento_unificacao u
        JOIN core.dim_evento m ON m.seed_origem='magento' AND m.seed_evento_id=u.magento_id
        WHERE s.origem='magento' AND s.evento_id_origem=u.magento_id
          AND s.criterio_vinculo='MANUAL_VALIDADO'
    """).rowcount
    marked = conn.execute("""
        UPDATE core.dim_evento d SET status_mapeamento='INDIVIDUAL',
            data_atualizacao_core=clock_timestamp()
        FROM core_evento_unificacao u
        WHERE d.status_mapeamento='UNIFICADO_VALIDADO'
          AND ((d.seed_origem='magento' AND d.seed_evento_id=u.magento_id)
            OR (d.seed_origem='ativo' AND d.seed_evento_id=u.ativo_id
                AND NOT EXISTS (SELECT 1 FROM core.evento_source_map o
                                WHERE o.evento_key=d.evento_key
                                  AND o.criterio_vinculo='MANUAL_VALIDADO')))
    """).rowcount
    return mapped, marked


def run(conn, command, decisions):
    # plan não pode ser READ ONLY (a tabela temporária é um CREATE); o
    # rollback forçado garante que nada persiste.
    with conn.transaction(force_rollback=command == "plan"):
        stage(conn, decisions)
        validate(conn)
        events, inscriptions, low, high = impact(conn)
        print(f"EVENT_UNIFY_PLAN events={events} inscriptions={inscriptions} "
              f"magento_inscricao_range={low}-{high}", flush=True)
        if command == "apply":
            mapped, marked = apply(conn)
            print(f"EVENT_UNIFY_APPLIED map_rows={mapped} dim_rows={marked}", flush=True)
        elif command == "revert":
            mapped, marked = revert(conn)
            print(f"EVENT_UNIFY_REVERTED map_rows={mapped} dim_rows={marked}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "apply", "revert"))
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--approve-production", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command != "plan" and not args.approve_production:
            raise RuntimeError("apply/revert exigem --approve-production")
        decisions = load_decisions(args.file)
        with local_raw_core.prevent_idle_sleep(), \
                local_raw_core.postgres_access(Settings.load()):
            settings = local_raw_core.local_settings()
            with local_raw_core.control_connection(settings) as (conn, _assert_control):
                run(conn, args.command, decisions)
        print("EVENT_UNIFY_OK", flush=True)
        return 0
    except Exception as exc:
        # Exceções de drivers podem conter SQL ou dados: só a classe.
        print(f"EVENT_UNIFY_FAILED {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

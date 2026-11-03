"""Atribuição de inscrições Ativo a combos vendidos (migrados ou não).

Regra aprovada em 03/11/2026 (Ativo é a origem oficial). A automação chama
`sync_changed` com os pedidos alterados no ciclo; `main` preenche o histórico.
"""

import argparse
import sys
from pathlib import Path

from src.core import runner

_V1 = Path(__file__).resolve().parents[2] / "sql/core/v1"
SQL = _V1 / "016_combo_atribuicao_ativo.sql"
VALIDADO_POR = "licencas.bi@cscdoesporte.com.br (regra COMBO_ATIVO)"
VALIDADO_EM = "2026-11-03T00:00:00-03:00"


def sync(conn, ativo_pedidos=None, todos=False):
    """Recalcula as atribuições do escopo numa transação; devolve linhas gravadas."""
    if not todos and not ativo_pedidos:
        return 0
    with conn.transaction():
        result = conn.execute(SQL.read_text(encoding="utf-8"), {
            "todos": todos,
            "ativo_pedidos": sorted(ativo_pedidos or ()),
            "validado_por": VALIDADO_POR,
            "validado_em": VALIDADO_EM,
        })
    return max(result.rowcount, 0)


def sync_changed(conn, orders):
    return sync(conn, orders.get("ativo"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--approve-production", action="store_true")
    args = parser.parse_args(argv)
    try:
        with runner.connect() as conn:
            runner.validate_destination(conn, args.approve_production)
            if not conn.execute("SELECT pg_try_advisory_lock(21001,1)").fetchone()[0]:
                raise RuntimeError("Outra execução CORE está ativa")
            conn.execute("SET statement_timeout=900000")
            written = sync(conn, todos=True)
            total = conn.execute(
                "SELECT count(*) FROM core.combo_inscricao_atribuicao").fetchone()[0]
        print(f"CORE_COMBO_ATRIBUICAO_OK gravadas={written} total={total}")
        return 0
    except Exception as exc:
        print(f"CORE_COMBO_ATRIBUICAO_FAILED {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

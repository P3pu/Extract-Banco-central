"""Executa checks de duplicidade das views STAGING sem expor linhas/PII."""

import argparse

from src.config.settings import ROOT, Settings
from src.db.postgres import connect


CHECKS = {"magento": ("900_validate_magento.sql", 14),
          "ativo": ("910_validate_ativo.sql", 18)}


def duplicate_queries(system):
    filename, count = CHECKS[system]
    path = ROOT / "sql" / "staging" / "validation" / filename
    lines = (line for line in path.read_text(encoding="utf-8").splitlines()
             if not line.lstrip().startswith("--"))
    statements = [query.strip() for query in "\n".join(lines).split(";") if query.strip()]
    return statements[:count]


def main():
    parser = argparse.ArgumentParser(description="Valida chaves das views STAGING")
    parser.add_argument("--system", choices=CHECKS, required=True)
    parser.add_argument("--start", type=int, default=1,
                        help="Número inicial do check (padrão: 1)")
    args = parser.parse_args()
    if args.start < 1 or args.start > CHECKS[args.system][1]:
        parser.error("--start fora do intervalo")
    with connect(Settings.load()) as connection:
        # Não alterar configurações permanentes do servidor de produção.
        connection.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        for index, query in enumerate(duplicate_queries(args.system), 1):
            if index < args.start:
                continue
            duplicates = connection.execute(
                f"SELECT COUNT(*) FROM ({query}) AS duplicadas").fetchone()[0]
            if duplicates:
                raise RuntimeError(f"Check {index}: {duplicates} chave(s) duplicada(s)")
            print(f"{args.system} check {index}: 0 duplicadas", flush=True)


if __name__ == "__main__":
    main()

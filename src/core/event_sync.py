"""Mesmo SKU é a mesma prova, e a data do Magento prevalece (decisão de 04/11/2026).

Roda uma vez por dia no ciclo. Une o evento Magento aos eventos Ativo de mesmo
SKU e mantém `core.dim_evento` em dia sem reprocessar faixas inteiras. Devolve as
inscrições afetadas para o diário da CORE.

Há SKU repetido em cidades diferentes no Ativo. Por isso, datas diferentes no lado
Ativo só unem com curadoria (`data/evento_sku_curadoria_20261104.csv`); sem ela, o
caso fica fora e é registrado no log.
"""

import csv
from pathlib import Path

from psycopg import Rollback

ROOT = Path(__file__).resolve().parents[2]
CURATION_FILE = ROOT / "sql/core/v1/data/evento_sku_curadoria_20261104.csv"
REVIEWER = "regra mesmo SKU aprovada em 04/11/2026"
# Acima disso o ciclo horário não dá conta: a execução é desfeita e fica no log.
MAX_DAILY_INSCRIPTIONS = 50_000

CANDIDATES = """
SELECT btrim(m.sku_referencia) sku, m.seed_evento_id magento_id, a.seed_evento_id ativo_id,
       a.data_evento, (SELECT count(*) FROM core.fato_inscricao f
                       WHERE f.evento_key=a.evento_key AND f.contabiliza_inscricao) inscritos
FROM core.dim_evento m
JOIN core.evento_source_map s ON s.origem='magento' AND s.evento_id_origem=m.seed_evento_id
JOIN core.dim_evento a ON a.seed_origem='ativo' AND a.flag_evento_teste IS NOT TRUE
 AND btrim(a.sku_referencia)=btrim(m.sku_referencia)
WHERE m.seed_origem='magento' AND m.status_mapeamento='INDIVIDUAL'
  AND s.criterio_vinculo='ORIGEM' AND btrim(m.sku_referencia)<>''
"""
# O evento principal fica com a data do Magento; o resto só segue a origem.
REFRESH_ATIVO = """
UPDATE core.dim_evento d SET data_evento=core.try_date(e.data_evento),
    data_evento_original=e.data_evento::text, data_atualizacao_core=clock_timestamp()
FROM staging.ativo_evento e
WHERE d.seed_origem='ativo' AND d.seed_evento_id=e.evento_id
  AND core.try_date(e.data_evento) IS NOT NULL
  AND d.data_evento IS DISTINCT FROM core.try_date(e.data_evento)
  AND NOT EXISTS (SELECT 1 FROM core.evento_source_map s
                  WHERE s.origem='magento' AND s.evento_key=d.evento_key)
RETURNING d.evento_key
"""
REFRESH_MAGENTO = """
UPDATE core.dim_evento d SET data_evento=e.data_evento::date,
    data_evento_original=e.data_evento::text, data_atualizacao_core=clock_timestamp()
FROM staging.magento_evento e
WHERE d.seed_origem='magento' AND d.seed_evento_id=e.evento_id
  AND e.data_evento IS NOT NULL AND d.data_evento IS DISTINCT FROM e.data_evento::date
RETURNING d.evento_key
"""
MAGENTO_DATE_WINS = """
UPDATE core.dim_evento d SET data_evento=x.data_magento, data_atualizacao_core=clock_timestamp()
FROM (SELECT s.evento_key, max(m.data_evento) data_magento
      FROM core.evento_source_map s
      JOIN core.dim_evento m ON m.seed_origem='magento' AND m.seed_evento_id=s.evento_id_origem
      WHERE s.origem='magento' AND s.evento_key<>m.evento_key AND m.data_evento IS NOT NULL
      GROUP BY 1) x
WHERE d.evento_key=x.evento_key AND d.data_evento IS DISTINCT FROM x.data_magento
RETURNING d.evento_key
"""


def load_curation(path=CURATION_FILE):
    curated = {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            curated.setdefault(row["sku"].strip(), set()).add(int(row["ativo_evento_id"]))
    if not curated:
        raise ValueError("Curadoria de SKU vazia")
    return curated


def build_decisions(rows, curated):
    """(sku, magento_id, principal, demais Ativo) e os SKUs que pedem revisão."""
    groups = {}
    for sku, magento_id, ativo_id, event_date, enrolled in rows:
        groups.setdefault((sku, magento_id), []).append((ativo_id, event_date, enrolled))
    decisions, review = [], []
    for (sku, magento_id), events in sorted(groups.items()):
        if sku in curated:
            events = [event for event in events if event[0] in curated[sku]]
        elif len({event[1] for event in events if event[1]}) > 1:
            review.append(sku)
            continue
        if not events:
            review.append(sku)
            continue
        # Mais inscritos primeiro; no empate, o menor ID, para o resultado ser estável.
        main = max(events, key=lambda event: (event[2], -event[0]))[0]
        decisions.append((sku, magento_id, main, sorted(e[0] for e in events if e[0] != main)))
    return decisions, review


def _keys_of(conn, origin, event_ids):
    return [row[0] for row in conn.execute(
        "SELECT evento_key FROM core.evento_source_map WHERE origem=%s AND evento_id_origem=ANY(%s::bigint[])",
        (origin, list(event_ids))).fetchall()]


def apply_decisions(conn, decisions):
    """Devolve as chaves antigas, para achar as inscrições que mudam de evento."""
    keys = set()
    for _sku, magento_id, main, others in decisions:
        keys.update(_keys_of(conn, "magento", [magento_id]))
        keys.update(_keys_of(conn, "ativo", [main, *others]))
        conn.execute("""
            UPDATE core.evento_source_map s
            SET evento_key=a.evento_key, criterio_vinculo='MANUAL_VALIDADO',
                revisado_por=%s, revisado_em=clock_timestamp()
            FROM core.dim_evento a
            WHERE a.seed_origem='ativo' AND a.seed_evento_id=%s
              AND ((s.origem='magento' AND s.evento_id_origem=%s)
                OR (s.origem='ativo' AND s.evento_id_origem=ANY(%s::bigint[])))
        """, (REVIEWER, main, magento_id, others))
        conn.execute("""
            UPDATE core.dim_evento SET status_mapeamento='UNIFICADO_VALIDADO',
                data_atualizacao_core=clock_timestamp()
            WHERE (seed_origem='magento' AND seed_evento_id=%s)
               OR (seed_origem='ativo' AND seed_evento_id=ANY(%s::bigint[]))
        """, (magento_id, [main, *others]))
    return keys


def refresh_dates(conn):
    keys = set()
    for query in (REFRESH_ATIVO, REFRESH_MAGENTO, MAGENTO_DATE_WINS):
        keys.update(row[0] for row in conn.execute(query).fetchall())
    return keys


def affected(conn, keys):
    """Inscrições das chaves dadas, no formato do diário da CORE."""
    if not keys:
        return []
    rows = conn.execute(
        "SELECT origem,inscricao_id_origem,pedido_id_origem FROM core.fato_inscricao "
        "WHERE evento_key=ANY(%s::bigint[])", (sorted(keys),)).fetchall()
    return [(origin, "inscription", source_id, order_id) for origin, source_id, order_id in rows]


def sync(conn, curated=None, maximum=MAX_DAILY_INSCRIPTIONS):
    """Numa transação só. `maximum=None` é para a carga inicial, feita em lotes à parte."""
    curated = load_curation() if curated is None else curated
    pending = []
    with conn.transaction():
        rows = conn.execute(CANDIDATES).fetchall()
        decisions, review = build_decisions(rows, curated)
        keys = apply_decisions(conn, decisions)
        keys |= refresh_dates(conn)
        pending = affected(conn, keys)
        print(f"EVENT_SYNC unificados={len(decisions)} chaves={len(keys)} "
              f"inscricoes={len(pending)} revisar={','.join(sorted(set(review))) or '-'}", flush=True)
        if maximum is not None and len(pending) > maximum:
            print("EVENT_SYNC_ADIADO volume acima do limite do ciclo", flush=True)
            pending = []
            raise Rollback()
    return pending

"""Atualização limitada da CORE a partir do diário de IDs RAW alterados."""

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from src.core import combo_attribution, runner
from src.core.person_dimension import sync_changed


SPAN = 100_000
MAX_RANGES_PER_SCOPE = 50
MAX_IDS_PER_INSCRIPTION_RANGE = 1_000
MAX_INSCRIPTION_RANGES = 100


def ranges(ids, *, span=SPAN, maximum=MAX_RANGES_PER_SCOPE):
    buckets = sorted({int(value) // span for value in ids})
    if len(buckets) > maximum:
        raise RuntimeError("Muitas faixas CORE; revisão de custo necessária")
    return [(bucket * span, (bucket + 1) * span - 1) for bucket in buckets]


def target_ranges(ids, *, span=SPAN, max_ids=MAX_IDS_PER_INSCRIPTION_RANGE,
                  maximum=MAX_INSCRIPTION_RANGES):
    """Particiona os IDs reais, sem recalcular uma faixa inteira por poucos IDs."""
    buckets = defaultdict(list)
    for value in sorted({int(value) for value in ids}):
        if value < 0:
            raise ValueError("ID CORE inválido")
        buckets[value // span].append(value)
    result = []
    for bucket in sorted(buckets):
        values = buckets[bucket]
        for start in range(0, len(values), max_ids):
            part = values[start:start + max_ids]
            result.append((part[0], part[-1], part))
    if len(result) > maximum:
        raise RuntimeError("Muitos lotes de inscrições CORE; revisão de custo necessária")
    return result


def affected_ids(conn, pending):
    """Pedidos alterados invalidam todas as inscrições existentes ligadas a eles."""
    orders = defaultdict(set)
    inscriptions = defaultdict(set)
    for origin, kind, source_id, order_id in pending:
        if origin not in {"ativo", "magento"} or kind not in {"order", "inscription"}:
            raise ValueError("Diário de alterações inválido")
        if kind == "order":
            orders[origin].add(source_id)
        else:
            inscriptions[origin].add(source_id)
        if order_id is not None:
            orders[origin].add(order_id)

    for origin in ("ativo", "magento"):
        # Inclui o pedido antigo caso uma inscrição tenha sido reassociada.
        for batch in _chunks(sorted(inscriptions[origin])):
            rows = conn.execute(
                "SELECT pedido_id_origem FROM core.fato_inscricao "
                "WHERE origem=%s AND inscricao_id_origem=ANY(%s::bigint[])",
                (origin, batch),
            ).fetchall()
            orders[origin].update(value for (value,) in rows if value is not None)
        # O índice core.fato_inscricao(origem,pedido_id_origem) cobre esta busca.
        for batch in _chunks(sorted(orders[origin])):
            rows = conn.execute(
                "SELECT inscricao_id_origem FROM core.fato_inscricao "
                "WHERE origem=%s AND pedido_id_origem=ANY(%s::bigint[])",
                (origin, batch),
            ).fetchall()
            inscriptions[origin].update(value for (value,) in rows)
    return orders, inscriptions


def _chunks(values, size=1000):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def refresh(conn, pending, assert_control=lambda: None):
    if not pending:
        return {"orders": 0, "inscriptions": 0}
    definition = conn.execute(
        "SELECT pg_get_viewdef('core.fato_inscricao_indicadores_validos'::regclass)"
    ).fetchone()[0]
    if "where false" not in definition.lower():
        raise RuntimeError("Gate de indicadores CORE aberto; automação recusada")
    orders, inscriptions = affected_ids(conn, pending)
    order_ranges = ranges(set().union(*orders.values()))
    inscription_ranges = target_ranges(set().union(*inscriptions.values()))
    as_of = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    for low, high in order_ranges:
        assert_control()
        runner.run_range(conn, "orders", low, high, as_of)
    # O contrato CORE já usa estas projeções temporárias em cargas por lotes.
    # Sem o cache, a reconciliação Magento revarre a RAW de itens por faixa.
    cached = len(inscription_ranges) > 1
    if cached:
        conn.execute("SET statement_timeout=300000")
        try:
            runner.prepare_inscription_cache(conn)
        finally:
            conn.execute("SET statement_timeout=60000")
    for low, high, selected in inscription_ranges:
        assert_control()
        runner.run_range(conn, "inscriptions", low, high, as_of, cached=cached,
                         selected_ids=selected)
    assert_control()
    with conn.transaction():
        contacts = sync_changed(conn, orders, inscriptions)
    print("CORE_PERSON_CONTACTS "
          f"installed={int(contacts['installed'])} "
          f"enabled={int(contacts['enabled'])} count={contacts['contacts']}",
          flush=True)
    assert_control()
    combos = combo_attribution.sync_changed(conn, orders)
    print(f"CORE_COMBO_ATRIBUICAO count={combos}", flush=True)
    assert_control()
    # A view deve permanecer fechada mesmo após todos os UPSERTs.
    if conn.execute(
        "SELECT count(*) FROM core.fato_inscricao_indicadores_validos"
    ).fetchone()[0] != 0:
        raise RuntimeError("Gate de indicadores CORE não está fechado")
    return {"orders": len(order_ranges), "inscriptions": len(inscription_ranges)}

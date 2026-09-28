"""Contrato validado no information_schema da origem em 2026-09-28."""
from datetime import timedelta

FIELDS = {
    "entity_id": ("int unsigned", "BIGINT", False),
    "increment_id": ("varchar(32)", "VARCHAR(32)", True),
    "customer_id": ("int unsigned", "BIGINT", True),
    "state": ("varchar(32)", "VARCHAR(32)", True),
    "status": ("varchar(32)", "VARCHAR(32)", True),
    "coupon_code": ("varchar(255)", "VARCHAR(255)", True),
    "applied_rule_ids": ("varchar(128)", "VARCHAR(128)", True),
    **{name: ("decimal(20,4)", "NUMERIC(20,4)", True) for name in (
        "subtotal", "base_subtotal", "discount_amount", "base_discount_amount",
        "shipping_amount", "base_shipping_amount", "tax_amount", "base_tax_amount",
        "grand_total", "base_grand_total")},
    "total_item_count": ("smallint unsigned", "INTEGER", False),
    "total_qty_ordered": ("decimal(12,4)", "NUMERIC(12,4)", True),
    "created_at": ("timestamp", "TIMESTAMP", False),
    "updated_at": ("timestamp", "TIMESTAMP", False),
}
COLUMNS = tuple(FIELDS)


def validate_schema(columns, indexes):
    actual = {c["COLUMN_NAME"]: c for c in columns}
    for name, (mysql_type, _, nullable) in FIELDS.items():
        if name not in actual or actual[name]["COLUMN_TYPE"].lower() != mysql_type:
            raise ValueError(f"Schema divergente: sales_order.{name}")
        if (actual[name]["IS_NULLABLE"] == "YES") != nullable:
            raise ValueError(f"Nullabilidade divergente: sales_order.{name}")
    pk = [x["COLUMN_NAME"] for x in indexes if x["INDEX_NAME"] == "PRIMARY"]
    if pk != ["entity_id"]:
        raise ValueError("PK de sales_order divergente")
    if not any(x["COLUMN_NAME"] == "updated_at" and x["SEQ_IN_INDEX"] == 1 for x in indexes):
        raise ValueError("Índice updated_at ausente")


def page_query(mode, batch_size, upper_id, upper_time, watermark=None, cursor=None):
    if batch_size <= 0 or mode not in {"FULL", "INCREMENTAL"}:
        raise ValueError("Modo ou lote inválido")
    fields = ", ".join(f"`{c}`" for c in COLUMNS)
    where = ["entity_id <= %s"]
    params = [upper_id]
    if mode == "FULL":
        if cursor is not None:
            where.append("entity_id > %s")
            params.append(cursor)
        order = "entity_id"
    else:
        if watermark is None:
            raise ValueError("Execute FULL antes do incremental")
        where.extend(["updated_at >= %s", "updated_at <= %s"])
        params.extend([watermark - timedelta(minutes=5), upper_time])
        if cursor is not None:
            where.append("(updated_at > %s OR (updated_at = %s AND entity_id > %s))")
            params.extend([cursor[0], cursor[0], cursor[1]])
        order = "updated_at, entity_id"
    params.append(batch_size)
    return (f"SELECT {fields} FROM sales_order WHERE {' AND '.join(where)} "
            f"ORDER BY {order} LIMIT %s", tuple(params))

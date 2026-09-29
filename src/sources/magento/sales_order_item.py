"""Campos reais de sales_order_item, inspecionados em 2026-09-28."""
from datetime import timedelta

PK = "item_id"
PAGE_BY_PK = True
FIELDS = {
    "item_id": ("int unsigned", "BIGINT", False),
    "order_id": ("int unsigned", "BIGINT", False),
    "parent_item_id": ("int unsigned", "BIGINT", True),
    "product_id": ("int unsigned", "BIGINT", True),
    **{n: ("varchar(255)", "VARCHAR(255)", True) for n in ("sku", "name", "product_type")},
    "additional_data": ("text", "TEXT", True),
    "ext_order_item_id": ("varchar(255)", "VARCHAR(255)", True),
    "ozone_customers": ("text", "TEXT", True),
    **{n: ("decimal(12,4)", "NUMERIC(12,4)", False) for n in ("price", "base_price")},
    **{n: ("decimal(20,4)", "NUMERIC(20,4)", False) for n in ("row_total", "base_row_total")},
    **{n: ("decimal(20,4)", "NUMERIC(20,4)", True) for n in (
        "discount_amount", "base_discount_amount", "tax_amount", "base_tax_amount")},
    **{n: ("decimal(12,4)", "NUMERIC(12,4)", True) for n in (
        "qty_ordered", "qty_invoiced", "qty_canceled", "qty_refunded")},
    "created_at": ("timestamp", "TIMESTAMP", False),
    "updated_at": ("timestamp", "TIMESTAMP", False),
}
COLUMNS = tuple(FIELDS)


def validate_schema(columns, indexes):
    actual = {c["COLUMN_NAME"]: c for c in columns}
    for name, (mysql_type, _, nullable) in FIELDS.items():
        if name not in actual or actual[name]["COLUMN_TYPE"].lower() != mysql_type:
            raise ValueError(f"Schema divergente: sales_order_item.{name}")
        if (actual[name]["IS_NULLABLE"] == "YES") != nullable:
            raise ValueError(f"Nullabilidade divergente: sales_order_item.{name}")
    if [x["COLUMN_NAME"] for x in indexes if x["INDEX_NAME"] == "PRIMARY"] != [PK]:
        raise ValueError("PK de sales_order_item divergente")


def page_query(mode, batch_size, upper_id, upper_time=None, watermark=None, cursor=None):
    if batch_size <= 0 or mode not in {"FULL", "INCREMENTAL"}:
        raise ValueError("Modo ou lote inválido")
    # updated_at não tem índice na origem. Percorrer a PK evita ordenar milhões
    # de linhas e continua encontrando atualizações em IDs antigos.
    where, params = ["item_id <= %s"], [upper_id]
    if cursor is not None:
        where.append("item_id > %s")
        params.append(cursor)
    if mode == "INCREMENTAL":
        if watermark is None:
            raise ValueError("Execute FULL antes do incremental")
        where.append("updated_at >= %s")
        params.append(watermark - timedelta(minutes=5))
    params.append(batch_size)
    fields = ", ".join(f"`{c}`" for c in COLUMNS)
    return (f"SELECT {fields} FROM sales_order_item FORCE INDEX (PRIMARY) "
            f"WHERE {' AND '.join(where)} ORDER BY item_id LIMIT %s", tuple(params))

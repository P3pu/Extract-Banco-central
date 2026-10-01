"""Contrato completo de salesrule, inspecionado no Magento em 2026-10-01."""

TABLE = "salesrule"
PK = "rule_id"
FIELDS = {
    "rule_id": ("int unsigned", "BIGINT", False),
    "name": ("varchar(255)", "VARCHAR(255)", True),
    "description": ("text", "TEXT", True),
    "from_date": ("date", "TEXT", True),
    "to_date": ("date", "TEXT", True),
    "uses_per_customer": ("int", "INTEGER", False),
    "is_active": ("smallint", "INTEGER", False),
    "conditions_serialized": ("mediumtext", "TEXT", True),
    "actions_serialized": ("mediumtext", "TEXT", True),
    "stop_rules_processing": ("smallint", "INTEGER", False),
    "is_advanced": ("smallint unsigned", "INTEGER", False),
    "product_ids": ("text", "TEXT", True),
    "sort_order": ("int unsigned", "BIGINT", False),
    "simple_action": ("varchar(32)", "VARCHAR(32)", True),
    "discount_amount": ("decimal(12,4)", "NUMERIC(12,4)", False),
    "discount_qty": ("decimal(12,4)", "NUMERIC(12,4)", True),
    "discount_step": ("int unsigned", "BIGINT", False),
    "apply_to_shipping": ("smallint unsigned", "INTEGER", False),
    "times_used": ("int unsigned", "BIGINT", False),
    "is_rss": ("smallint", "INTEGER", False),
    "coupon_type": ("smallint unsigned", "INTEGER", False),
    "use_auto_generation": ("smallint", "INTEGER", False),
    "uses_per_coupon": ("int", "INTEGER", False),
    "updated_at": ("timestamp", "TEXT", True),
    "created_at": ("timestamp", "TEXT", True),
    "simple_free_shipping": ("smallint unsigned", "INTEGER", False),
}
COLUMNS = tuple(FIELDS)


def validate_schema(columns, indexes):
    actual = {column["COLUMN_NAME"]: column for column in columns}
    if len(actual) != len(FIELDS):
        raise ValueError(f"Schema divergente: {TABLE} ganhou/perdeu colunas")
    for name, (mysql_type, _, nullable) in FIELDS.items():
        column = actual.get(name)
        if column is None or column["COLUMN_TYPE"].lower() != mysql_type:
            raise ValueError(f"Schema divergente: {TABLE}.{name}")
        if (column["IS_NULLABLE"] == "YES") != nullable:
            raise ValueError(f"Nullabilidade divergente: {TABLE}.{name}")
    if [item["COLUMN_NAME"] for item in indexes if item["INDEX_NAME"] == "PRIMARY"] != [PK]:
        raise ValueError(f"PK de {TABLE} divergente")


def page_query(batch_size, upper_id, cursor=None):
    if batch_size <= 0 or upper_id is None:
        raise ValueError("Lote ou limite inválido")
    where, params = [f"`{PK}` <= %s"], [upper_id]
    if cursor is not None:
        where.append(f"`{PK}` > %s")
        params.append(cursor)
    params.append(batch_size)
    fields = ", ".join(f"`{name}`" for name in COLUMNS)
    return (f"SELECT {fields} FROM `{TABLE}` FORCE INDEX (PRIMARY) "
            f"WHERE {' AND '.join(where)} ORDER BY `{PK}` LIMIT %s", tuple(params))

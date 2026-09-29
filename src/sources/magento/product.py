"""Campos de catalog_product_entity validados no Magento em 2026-09-29."""

from datetime import timedelta

TABLE = "catalog_product_entity"
PK = "entity_id"
PAGE_BY_PK = True
FIELDS = {
    "entity_id": ("int unsigned", "BIGINT", False),
    "sku": ("varchar(64)", "VARCHAR(64)", True),
    "type_id": ("varchar(32)", "VARCHAR(32)", False),
    "attribute_set_id": ("smallint unsigned", "INTEGER", False),
    "created_at": ("timestamp", "TIMESTAMP", False),
    "updated_at": ("timestamp", "TIMESTAMP", False),
}
COLUMNS = tuple(FIELDS)


def validate_schema(columns, indexes):
    actual = {column["COLUMN_NAME"]: column for column in columns}
    for name, (mysql_type, _, nullable) in FIELDS.items():
        column = actual.get(name)
        if column is None or column["COLUMN_TYPE"].lower() != mysql_type:
            raise ValueError(f"Schema divergente: {TABLE}.{name}")
        if (column["IS_NULLABLE"] == "YES") != nullable:
            raise ValueError(f"Nullabilidade divergente: {TABLE}.{name}")
    if [item["COLUMN_NAME"] for item in indexes if item["INDEX_NAME"] == "PRIMARY"] != [PK]:
        raise ValueError(f"PK de {TABLE} divergente")


def page_query(mode, batch_size, upper_id, upper_time=None, watermark=None, cursor=None):
    if mode not in {"FULL", "INCREMENTAL"} or batch_size <= 0 or upper_id is None:
        raise ValueError("Modo, lote ou limite inválido")
    where, params = [f"`{PK}` <= %s"], [upper_id]
    if cursor is not None:
        where.append(f"`{PK}` > %s")
        params.append(cursor)
    if mode == "INCREMENTAL":
        if watermark is None:
            raise ValueError("Execute FULL antes do incremental")
        where.append("`updated_at` >= %s")
        params.append(watermark - timedelta(minutes=5))
    params.append(batch_size)
    fields = ", ".join(f"`{name}`" for name in COLUMNS)
    return (f"SELECT {fields} FROM `{TABLE}` FORCE INDEX (PRIMARY) "
            f"WHERE {' AND '.join(where)} ORDER BY `{PK}` LIMIT %s", tuple(params))

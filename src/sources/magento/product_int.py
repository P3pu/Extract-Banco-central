"""EAV int do produto Magento: somente atributos 194, 206 e 207."""

TABLE = "catalog_product_entity_int"
PK = "value_id"
ATTRIBUTES = (194, 206, 207)
FIELDS = {
    "value_id": ("int", "INTEGER", False),
    "attribute_id": ("smallint unsigned", "INTEGER", False),
    "store_id": ("smallint unsigned", "INTEGER", False),
    "entity_id": ("int unsigned", "BIGINT", False),
    "value": ("int", "INTEGER", True),
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
    if not any(item["COLUMN_NAME"] == "attribute_id" and item["SEQ_IN_INDEX"] == 1
               for item in indexes):
        raise ValueError(f"Índice de atributo ausente em {TABLE}")


def page_query(batch_size, upper_id, cursor=None):
    if batch_size <= 0 or upper_id is None:
        raise ValueError("Lote ou limite inválido")
    where = ["`attribute_id` IN (%s, %s, %s)", f"`{PK}` <= %s"]
    params = [*ATTRIBUTES, upper_id]
    if cursor is not None:
        where.append(f"`{PK}` > %s")
        params.append(cursor)
    params.append(batch_size)
    fields = ", ".join(f"`{name}`" for name in COLUMNS)
    return (f"SELECT {fields} FROM `{TABLE}` FORCE INDEX (PRIMARY) "
            f"WHERE {' AND '.join(where)} ORDER BY `{PK}` LIMIT %s", tuple(params))

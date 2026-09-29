"""Metadados EAV Magento: somente os seis atributos de produto solicitados."""

TABLE = "eav_attribute"
PK = "attribute_id"
ATTRIBUTES = (73, 194, 195, 206, 207, 321)
FIELDS = {
    "attribute_id": ("smallint unsigned", "INTEGER", False),
    "attribute_code": ("varchar(255)", "VARCHAR(255)", False),
    "backend_type": ("varchar(8)", "VARCHAR(8)", False),
    "frontend_input": ("varchar(50)", "VARCHAR(50)", True),
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


def page_query(batch_size, upper_id, cursor=None):
    if batch_size <= 0 or upper_id is None:
        raise ValueError("Lote ou limite inválido")
    marks = ", ".join(["%s"] * len(ATTRIBUTES))
    where = [f"`{PK}` IN ({marks})", f"`{PK}` <= %s"]
    params = [*ATTRIBUTES, upper_id]
    if cursor is not None:
        where.append(f"`{PK}` > %s")
        params.append(cursor)
    params.append(batch_size)
    fields = ", ".join(f"`{name}`" for name in COLUMNS)
    return (f"SELECT {fields} FROM `{TABLE}` FORCE INDEX (PRIMARY) "
            f"WHERE {' AND '.join(where)} ORDER BY `{PK}` LIMIT %s", tuple(params))

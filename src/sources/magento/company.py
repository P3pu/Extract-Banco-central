"""Cadastro de empresas Magento: seis campos solicitados, PK id."""

TABLE = "aw_ca_company"
PK = "id"
FIELDS = {
    "id": ("int unsigned", "BIGINT", False),
    "root_group_id": ("int unsigned", "BIGINT", False),
    "status": ("varchar(20)", "VARCHAR(20)", False),
    "name": ("varchar(255)", "VARCHAR(255)", False),
    "legal_name": ("varchar(255)", "VARCHAR(255)", True),
    "email": ("varchar(100)", "VARCHAR(100)", False),
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
    where, params = [f"`{PK}` <= %s"], [upper_id]
    if cursor is not None:
        where.append(f"`{PK}` > %s")
        params.append(cursor)
    params.append(batch_size)
    fields = ", ".join(f"`{name}`" for name in COLUMNS)
    return (f"SELECT {fields} FROM `{TABLE}` FORCE INDEX (PRIMARY) "
            f"WHERE {' AND '.join(where)} ORDER BY `{PK}` LIMIT %s", tuple(params))

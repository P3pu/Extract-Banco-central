"""Contrato mínimo de sa_evento confirmado no MySQL Ativo em 2026-09-28."""

PK = "id_evento"
FIELDS = {
    "id_evento": ("int(11)", "INTEGER", False),
    "id_campanha_salesforce": ("varchar(50)", "VARCHAR(50)", True),
    "ds_evento": ("varchar(100)", "VARCHAR(100)", False),
    # Há DATETIME zero na origem. TEXT preserva a representação literal.
    "dt_evento": ("datetime", "TEXT", True),
    "hr_evento": ("varchar(20)", "VARCHAR(20)", True),
    "id_pais_origem": ("int(10)", "INTEGER", True),
    "data_update": ("timestamp", "TIMESTAMP", True),
    "dt_modificacao": ("datetime", "TEXT", True),
}
COLUMNS = tuple(FIELDS)


def validate_schema(columns, indexes):
    actual = {item["COLUMN_NAME"]: item for item in columns}
    for name, (mysql_type, _, nullable) in FIELDS.items():
        if name not in actual or actual[name]["COLUMN_TYPE"].lower() != mysql_type:
            raise ValueError(f"Schema divergente: sa_evento.{name}")
        if (actual[name]["IS_NULLABLE"] == "YES") != nullable:
            raise ValueError(f"Nullabilidade divergente: sa_evento.{name}")
    if [item["COLUMN_NAME"] for item in indexes if item["INDEX_NAME"] == "PRIMARY"] != [PK]:
        raise ValueError("PK de sa_evento divergente")


def page_query(batch_size, upper_id, cursor=None):
    if batch_size <= 0 or upper_id is None:
        raise ValueError("Lote ou limite inválido")
    fields = ", ".join(
        f"CAST(e.`{name}` AS CHAR)" if name in {"dt_evento", "dt_modificacao"}
        else f"e.`{name}`" for name in COLUMNS)
    where = ["e.id_evento <= %s"]
    params = [upper_id]
    if cursor is not None:
        where.append("e.id_evento > %s")
        params.append(cursor)
    params.append(batch_size)
    return (f"SELECT {fields} FROM sa_evento e FORCE INDEX (PRIMARY) "
            f"WHERE {' AND '.join(where)} ORDER BY e.id_evento LIMIT %s", tuple(params))

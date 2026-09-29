"""Contrato RAW de sa_cupom_desconto_item validado no MySQL Ativo."""

PK = "id_cupom_desconto_item"
TABLE = "sa_cupom_desconto_item"
TEXT_DATES = ("dt_sistema", "dt_uso")
FIELDS = {
    "id_cupom_desconto_item": ("int(10) unsigned", "BIGINT", False),
    "nr_cupom": ("varchar(45)", "VARCHAR(45)", False),
    # CHAR(1) pode devolver string vazia; VARCHAR(1) preserva esse valor na RAW.
    "fl_usado": ("char(1)", "VARCHAR(1)", False),
    "ds_ip": ("varchar(15)", "VARCHAR(15)", True),
    # TEXT preserva datas zero existentes ou futuras sem normalização.
    "dt_sistema": ("datetime", "TEXT", False),
    "dt_uso": ("datetime", "TEXT", True),
    "id_cupom_desconto": ("int(10) unsigned", "BIGINT", False),
    "id_evento": ("int(10)", "INTEGER", True),
    "fl_reserva": ("int(1) unsigned", "BIGINT", True),
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


def _select_fields():
    return ", ".join(
        f"CAST(c.`{name}` AS CHAR)" if name in TEXT_DATES else f"c.`{name}`"
        for name in COLUMNS)


def page_query(batch_size, upper_id, cursor=None):
    if batch_size <= 0 or upper_id is None:
        raise ValueError("Lote ou limite inválido")
    where = [f"c.`{PK}` <= %s"]
    params = [upper_id]
    if cursor is not None:
        where.append(f"c.`{PK}` > %s")
        params.append(cursor)
    params.append(batch_size)
    return (f"SELECT {_select_fields()} FROM `{TABLE}` c FORCE INDEX (PRIMARY) "
            f"WHERE {' AND '.join(where)} ORDER BY c.`{PK}` LIMIT %s", tuple(params))


def ids_query(ids, upper_id):
    if not ids or upper_id is None:
        raise ValueError("IDs e limite obrigatórios")
    marks = ", ".join(["%s"] * len(ids))
    return (f"SELECT {_select_fields()} FROM `{TABLE}` c FORCE INDEX (PRIMARY) "
            f"WHERE c.`{PK}` IN ({marks}) AND c.`{PK}` <= %s ORDER BY c.`{PK}`",
            (*ids, upper_id))

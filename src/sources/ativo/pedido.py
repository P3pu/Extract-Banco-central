"""Contrato de sa_pedido validado no Ativo MySQL 5.7 em 2026-09-28."""

PK = "id_pedido"
FIELDS = {
    "id_pedido": ("int(11)", "INTEGER", False),
    "id_pedido_status": ("int(11)", "INTEGER", False),
    "id_combo": ("int(10) unsigned", "BIGINT", True),
    "id_cupom_desconto_item": ("int(11)", "INTEGER", True),
    "ds_cod": ("varchar(25)", "VARCHAR(25)", True),
    # MySQL armazena datas zero que PostgreSQL TIMESTAMP rejeita. TEXT preserva
    # tanto as 304 datas zero observadas como o horário original sem conversão.
    "dt_pedido": ("timestamp", "TEXT", False),
    "dt_alteracao": ("timestamp", "TEXT", True),
    "fl_local_inscricao": ("int(1)", "INTEGER", True),
    "fl_delivery": ("char(1)", "CHAR(1)", True),
    "fl_mobile": ("int(1)", "INTEGER", True),
    "fl_assinante": ("int(1)", "INTEGER", True),
    "fl_evento_da_casa": ("int(1)", "INTEGER", True),
    "nr_taxa": ("decimal(10,2)", "NUMERIC(10,2)", True),
    "nr_delivery": ("decimal(10,2)", "NUMERIC(10,2)", True),
    "nr_desconto": ("decimal(10,2)", "NUMERIC(10,2)", False),
    "tp_entregakit": ("int(1)", "INTEGER", True),
    "nm_camiseta": ("varchar(150)", "VARCHAR(150)", True),
    "ds_campo_apolo": ("varchar(100)", "VARCHAR(100)", True),
    "ds_obs": ("varchar(150)", "VARCHAR(150)", True),
}
COLUMNS = tuple(FIELDS)


def validate_schema(columns, indexes):
    actual = {c["COLUMN_NAME"]: c for c in columns}
    for name, (mysql_type, _, nullable) in FIELDS.items():
        if name not in actual or actual[name]["COLUMN_TYPE"].lower() != mysql_type:
            raise ValueError(f"Schema divergente: sa_pedido.{name}")
        if (actual[name]["IS_NULLABLE"] == "YES") != nullable:
            raise ValueError(f"Nullabilidade divergente: sa_pedido.{name}")
    if [x["COLUMN_NAME"] for x in indexes if x["INDEX_NAME"] == "PRIMARY"] != [PK]:
        raise ValueError("PK de sa_pedido divergente")
    if not any(x["COLUMN_NAME"] == "dt_pedido" and x["SEQ_IN_INDEX"] == 1 for x in indexes):
        raise ValueError("Índice dt_pedido ausente")


def page_query(mode, batch_size, upper_id, cursor=None, cutoff=None):
    if batch_size <= 0 or mode not in {"FULL", "INCREMENTAL", "RECONCILIATION"}:
        raise ValueError("Modo ou lote inválido")
    fields = ", ".join(f"`{name}`" for name in COLUMNS)
    where, params = ["id_pedido <= %s"], [upper_id]
    if mode == "RECONCILIATION":
        if cutoff is None:
            raise ValueError("Janela de reconciliação obrigatória")
        where.append("dt_pedido >= %s")
        params.append(cutoff)
        if cursor is not None:
            where.append("(dt_pedido > %s OR (dt_pedido = %s AND id_pedido > %s))")
            params.extend((cursor[0], cursor[0], cursor[1]))
        order = "dt_pedido, id_pedido"
        hint = "FORCE INDEX (dt_pedido)"
    else:
        if cursor is not None:
            where.append("id_pedido > %s")
            params.append(cursor)
        order = "id_pedido"
        hint = "FORCE INDEX (PRIMARY)"
    params.append(batch_size)
    return (f"SELECT {fields} FROM sa_pedido {hint} WHERE {' AND '.join(where)} "
            f"ORDER BY {order} LIMIT %s", tuple(params))

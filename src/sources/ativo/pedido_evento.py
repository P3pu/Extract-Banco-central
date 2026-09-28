"""Contrato de sa_pedido_evento validado no Ativo MySQL 5.7."""

PK = "id_pedido_evento"
FIELDS = {
    "id_pedido_evento": ("int(11)", "INTEGER", False),
    "id_pedido": ("int(11)", "INTEGER", False),
    "id_evento": ("int(11)", "INTEGER", False),
    "id_modalidade": ("int(11)", "INTEGER", True),
    "id_categoria": ("int(11)", "INTEGER", True),
    "id_usuario": ("int(11)", "INTEGER", False),
    "id_usuario_balcao": ("int(10) unsigned", "BIGINT", True),
    "id_tamanho_camiseta": ("int(11)", "INTEGER", True),
    "id_status_detalhado": ("int(2)", "INTEGER", True),
    "id_cupom_individual": ("int(10)", "INTEGER", True),
    "nr_peito": ("int(5)", "INTEGER", True),
    "nr_preco": ("decimal(10,2)", "NUMERIC(10,2)", False),
    "nr_taxa": ("decimal(10,4)", "NUMERIC(10,4)", True),
    "nr_desconto_individual": ("varchar(150)", "VARCHAR(150)", True),
    "nr_protocolo_revezamento": ("int(11)", "INTEGER", True),
    "nr_ordem_revezamento": ("int(11)", "INTEGER", True),
    "fl_capitao_revezamento": ("int(1)", "INTEGER", True),
    "fl_assinante": ("int(1)", "INTEGER", True),
    # MySQL CHAR(1) pode devolver string vazia; PostgreSQL CHAR(1) a preenche com espaço.
    "fl_amigo": ("char(1)", "VARCHAR(1)", False),
    "pos_id_evento": ("int(11)", "INTEGER", True),
    "pos_id_pedido": ("int(11)", "INTEGER", True),
    "pos_id_pedido_evento": ("int(11)", "INTEGER", True),
    "ds_equipe": ("varchar(50)", "VARCHAR(50)", True),
    "ds_nome_equipe_revezamento": ("varchar(100)", "VARCHAR(100)", True),
    "ds_obs": ("varchar(200)", "VARCHAR(200)", True),
    "nm_camiseta": ("varchar(150)", "VARCHAR(150)", True),
    "nr_preco_nm_camiseta": ("varchar(150)", "VARCHAR(150)", True),
    "nr_preco_foto_clube": ("varchar(150)", "VARCHAR(150)", True),
    "nr_preco_personalizacao_medalha": ("varchar(150)", "VARCHAR(150)", True),
    "dt_cadastro": ("timestamp", "TIMESTAMP", False),
}
COLUMNS = tuple(FIELDS)


def validate_schema(columns, indexes):
    actual = {c["COLUMN_NAME"]: c for c in columns}
    for name, (mysql_type, _, nullable) in FIELDS.items():
        if name not in actual or actual[name]["COLUMN_TYPE"].lower() != mysql_type:
            raise ValueError(f"Schema divergente: sa_pedido_evento.{name}")
        if (actual[name]["IS_NULLABLE"] == "YES") != nullable:
            raise ValueError(f"Nullabilidade divergente: sa_pedido_evento.{name}")
    if [x["COLUMN_NAME"] for x in indexes if x["INDEX_NAME"] == "PRIMARY"] != [PK]:
        raise ValueError("PK de sa_pedido_evento divergente")
    if not any(x["COLUMN_NAME"] == "id_pedido" and x["SEQ_IN_INDEX"] == 1 for x in indexes):
        raise ValueError("Índice id_pedido ausente")


def page_query(mode, batch_size, upper_id, cursor=None, cutoff=None):
    if batch_size <= 0 or mode not in {"FULL", "INCREMENTAL", "RECONCILIATION"}:
        raise ValueError("Modo ou lote inválido")
    fields = ", ".join(f"pe.`{name}`" for name in COLUMNS)
    if mode == "RECONCILIATION":
        if cutoff is None:
            raise ValueError("Janela de reconciliação obrigatória")
        # A origem tem índice em p.dt_pedido e pe.id_pedido. STRAIGHT_JOIN
        # começa pelos pedidos recentes; não faz GROUP BY nem DISTINCT.
        from_part = ("sa_pedido p FORCE INDEX (dt_pedido) STRAIGHT_JOIN "
                     "sa_pedido_evento pe FORCE INDEX (id_pedido) ON pe.id_pedido = p.id_pedido")
        where, params = ["p.dt_pedido >= %s", "pe.id_pedido_evento <= %s"], [cutoff, upper_id]
        if cursor is not None:
            where.append("pe.id_pedido_evento > %s")
            params.append(cursor)
    else:
        from_part = "sa_pedido_evento pe FORCE INDEX (PRIMARY)"
        where, params = ["pe.id_pedido_evento <= %s"], [upper_id]
        if cursor is not None:
            where.append("pe.id_pedido_evento > %s")
            params.append(cursor)
    params.append(batch_size)
    return (f"SELECT {fields} FROM {from_part} WHERE {' AND '.join(where)} "
            "ORDER BY pe.id_pedido_evento LIMIT %s", tuple(params))

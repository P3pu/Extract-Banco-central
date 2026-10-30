"""Campos mínimos de produtos de pedido, endereços e cabeçalho de cupom, conferidos no Ativo."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ComplementoContract:
    TABLE: str
    PK: str
    FIELDS: dict
    RECONCILE_BY_ORDER: bool = False

    @property
    def COLUMNS(self):
        return tuple(self.FIELDS)

    def validate_schema(self, columns, indexes):
        actual = {column["COLUMN_NAME"]: column for column in columns}
        for name, (mysql_type, _, nullable) in self.FIELDS.items():
            column = actual.get(name)
            actual_type = column["COLUMN_TYPE"].lower() if column is not None else None
            # ENUM: novos valores na origem não quebram a carga; a RAW guarda texto.
            matches = (actual_type.startswith("enum(") if mysql_type == "enum"
                       else actual_type == mysql_type) if actual_type else False
            if not matches:
                raise ValueError(f"Schema divergente: {self.TABLE}.{name}")
            if (column["IS_NULLABLE"] == "YES") != nullable:
                raise ValueError(f"Nullabilidade divergente: {self.TABLE}.{name}")
        if [item["COLUMN_NAME"] for item in indexes if item["INDEX_NAME"] == "PRIMARY"] != [self.PK]:
            raise ValueError(f"PK de {self.TABLE} divergente")
        if self.RECONCILE_BY_ORDER and not any(
                item["INDEX_NAME"] == "id_pedido" and item["COLUMN_NAME"] == "id_pedido"
                and item["SEQ_IN_INDEX"] == 1 for item in indexes):
            raise ValueError(f"Índice id_pedido ausente em {self.TABLE}")

    def page_query(self, batch_size, upper_id, cursor=None):
        if batch_size <= 0 or upper_id is None:
            raise ValueError("Lote ou limite inválido")
        fields = ", ".join(f"t.`{name}`" for name in self.COLUMNS)
        where = [f"t.`{self.PK}` <= %s"]
        params = [upper_id]
        if cursor is not None:
            where.append(f"t.`{self.PK}` > %s")
            params.append(cursor)
        params.append(batch_size)
        return (f"SELECT {fields} FROM `{self.TABLE}` t FORCE INDEX (PRIMARY) "
                f"WHERE {' AND '.join(where)} ORDER BY t.`{self.PK}` LIMIT %s", tuple(params))

    def reconcile_page_query(self, cutoff, upper_id, batch_size, cursor=None):
        if not self.RECONCILE_BY_ORDER or cutoff is None or upper_id is None or batch_size <= 0:
            raise ValueError("Reconciliação inválida")
        fields = ", ".join(f"e.`{name}`" for name in self.COLUMNS)
        where = ["p.dt_pedido >= %s", f"e.`{self.PK}` <= %s"]
        params = [cutoff, upper_id]
        if cursor is not None:
            where.append(f"e.`{self.PK}` > %s")
            params.append(cursor)
        params.append(batch_size)
        return (f"SELECT {fields} FROM sa_pedido p FORCE INDEX (dt_pedido) "
                f"STRAIGHT_JOIN `{self.TABLE}` e FORCE INDEX (id_pedido) "
                f"ON e.id_pedido = p.id_pedido WHERE {' AND '.join(where)} "
                f"ORDER BY e.`{self.PK}` LIMIT %s", tuple(params))


pedido_produto = ComplementoContract(
    TABLE="sa_pedido_produto", PK="id_pedido_produto",
    FIELDS={
        "id_pedido_produto": ("int(11)", "INTEGER", False),
        "id_pedido": ("int(11)", "INTEGER", False),
        "id_produto": ("int(11)", "INTEGER", False),
        "nr_preco": ("decimal(10,2)", "NUMERIC(10,2)", False),
        "nr_quantidade": ("int(5)", "INTEGER", False),
    })

pedido_endereco = ComplementoContract(
    TABLE="sa_pedido_endereco", PK="id_pedido_endereco", RECONCILE_BY_ORDER=True,
    FIELDS={
        "id_pedido_endereco": ("int(11)", "INTEGER", False),
        "id_pedido": ("int(11)", "INTEGER", False),
        "id_pedido_evento": ("int(11)", "INTEGER", True),
        "id_cidade": ("int(11)", "INTEGER", False),
        "ds_endereco": ("varchar(255)", "VARCHAR(255)", False),
        "ds_num": ("varchar(20)", "VARCHAR(20)", False),
        "ds_complemento": ("varchar(20)", "VARCHAR(20)", False),
        "ds_bairro": ("varchar(100)", "VARCHAR(100)", False),
        "nr_cep": ("varchar(10)", "VARCHAR(10)", False),
        "dt_cadastro": ("timestamp", "TIMESTAMP", False),
    })

# Cabeçalho do cupom (26,5 mil linhas em 30/10/2026): snapshot diário completo.
# A classificação é dado de origem, não regra; vazia ou NULL não gera pendência.
cupom_desconto = ComplementoContract(
    TABLE="sa_cupom_desconto", PK="id_cupom_desconto",
    FIELDS={
        "id_cupom_desconto": ("int(10) unsigned", "BIGINT", False),
        "en_cupom_classificacao": ("enum", "TEXT", True),
    })

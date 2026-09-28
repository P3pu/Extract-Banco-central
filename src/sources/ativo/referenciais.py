"""Contratos dos referenciais Ativo validados no MySQL em 2026-09-28."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SnapshotReference:
    TABLE: str
    PK: str
    FIELDS: dict
    TEXT_DATES: tuple = ()

    @property
    def COLUMNS(self):
        return tuple(self.FIELDS)

    def validate_schema(self, columns, indexes):
        actual = {item["COLUMN_NAME"]: item for item in columns}
        for name, (mysql_type, _, nullable) in self.FIELDS.items():
            if name not in actual or actual[name]["COLUMN_TYPE"].lower() != mysql_type:
                raise ValueError(f"Schema divergente: {self.TABLE}.{name}")
            if (actual[name]["IS_NULLABLE"] == "YES") != nullable:
                raise ValueError(f"Nullabilidade divergente: {self.TABLE}.{name}")
        if [item["COLUMN_NAME"] for item in indexes if item["INDEX_NAME"] == "PRIMARY"] != [self.PK]:
            raise ValueError(f"PK de {self.TABLE} divergente")

    def page_query(self, batch_size, upper_id, cursor=None):
        if batch_size <= 0 or upper_id is None:
            raise ValueError("Lote ou limite inválido")
        fields = ", ".join(
            f"CAST(t.`{name}` AS CHAR)" if name in self.TEXT_DATES else f"t.`{name}`"
            for name in self.COLUMNS)
        where = [f"t.`{self.PK}` <= %s"]
        params = [upper_id]
        if cursor is not None:
            where.append(f"t.`{self.PK}` > %s")
            params.append(cursor)
        params.append(batch_size)
        return (f"SELECT {fields} FROM `{self.TABLE}` t FORCE INDEX (PRIMARY) "
                f"WHERE {' AND '.join(where)} ORDER BY t.`{self.PK}` LIMIT %s", tuple(params))


evento_modalidade = SnapshotReference(
    TABLE="sa_evento_modalidade", PK="id_modalidade",
    FIELDS={
        "id_modalidade": ("int(11)", "INTEGER", False),
        "nm_modalidade": ("varchar(100)", "VARCHAR(100)", False),
        "ds_horario": ("varchar(150)", "VARCHAR(150)", True),
        "nr_ordem": ("int(10)", "INTEGER", True),
        "data_update": ("timestamp", "TEXT", True),
    }, TEXT_DATES=("data_update",))

modalidade_categoria = SnapshotReference(
    TABLE="sa_modalidade_categoria", PK="id_categoria",
    FIELDS={
        "id_categoria": ("int(11)", "INTEGER", False),
        "ds_categoria": ("varchar(100)", "VARCHAR(100)", False),
        "vl_kit": ("decimal(10,2)", "NUMERIC(10,2)", True),
        "data_update": ("timestamp", "TIMESTAMP", True),
    })

pedido_status = SnapshotReference(
    TABLE="sa_pedido_status", PK="id_pedido_status",
    FIELDS={
        "id_pedido_status": ("int(11)", "INTEGER", False),
        "ds_status": ("varchar(50)", "VARCHAR(50)", False),
    })

tamanho_camiseta = SnapshotReference(
    TABLE="sa_tamanho_camiseta", PK="id_tamanho_camiseta",
    FIELDS={
        "id_tamanho_camiseta": ("int(11)", "INTEGER", False),
        "ds_tamanho": ("varchar(50)", "VARCHAR(50)", False),
        "nr_peso": ("decimal(10,2)", "NUMERIC(10,2)", True),
        "vl_valor": ("decimal(10,2)", "NUMERIC(10,2)", True),
        "id_situacao_cadastro": ("int(11)", "INTEGER", False),
        "disponivel_atleta": ("int(1)", "INTEGER", False),
        "id_pais_origem": ("int(11)", "INTEGER", True),
    })

formas_pagamento = SnapshotReference(
    TABLE="sa_formas_pagamento", PK="id_formas_pagamento",
    FIELDS={
        "id_formas_pagamento": ("int(10)", "INTEGER", False),
        "ds_descricao": ("varchar(255)", "VARCHAR(255)", True),
    })

produto = SnapshotReference(
    TABLE="sa_produto", PK="id_produto",
    FIELDS={
        "id_produto": ("int(10) unsigned", "BIGINT", False),
        "ds_titulo": ("varchar(250)", "VARCHAR(250)", False),
        "data_update": ("timestamp", "TIMESTAMP", True),
    })

combo = SnapshotReference(
    TABLE="sa_combo", PK="id_combo",
    FIELDS={
        "id_combo": ("int(10) unsigned", "BIGINT", False),
        "ds_titulo": ("varchar(60)", "VARCHAR(60)", False),
    })

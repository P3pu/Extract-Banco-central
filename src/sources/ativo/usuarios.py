"""Contratos mínimos dos cadastros de usuários Ativo, conferidos em 2026-09-28."""

from dataclasses import dataclass


@dataclass(frozen=True)
class UsuarioContract:
    TABLE: str
    FIELDS: dict
    TEXT_DATES: tuple
    PK: str = "id_usuario"

    @property
    def COLUMNS(self):
        return tuple(self.FIELDS)

    def validate_schema(self, columns, indexes):
        actual = {item["COLUMN_NAME"]: item for item in columns}
        for name, (mysql_type, _, nullable) in self.FIELDS.items():
            column = actual.get(name)
            if column is None:
                raise ValueError(f"Schema divergente: {self.TABLE}.{name}")
            if mysql_type == "enum":
                valid_type = column["DATA_TYPE"].lower() == "enum"
            else:
                valid_type = column["COLUMN_TYPE"].lower() == mysql_type
            if not valid_type or (column["IS_NULLABLE"] == "YES") != nullable:
                raise ValueError(f"Schema divergente: {self.TABLE}.{name}")
        if [item["COLUMN_NAME"] for item in indexes if item["INDEX_NAME"] == "PRIMARY"] != [self.PK]:
            raise ValueError(f"PK de {self.TABLE} divergente")

    def page_query(self, batch_size, upper_id, cursor=None):
        if batch_size <= 0 or upper_id is None:
            raise ValueError("Lote ou limite inválido")
        fields = ", ".join(
            f"CAST(u.`{name}` AS CHAR)" if name in self.TEXT_DATES else f"u.`{name}`"
            for name in self.COLUMNS)
        where = [f"u.`{self.PK}` <= %s"]
        params = [upper_id]
        if cursor is not None:
            where.append(f"u.`{self.PK}` > %s")
            params.append(cursor)
        params.append(batch_size)
        return (f"SELECT {fields} FROM `{self.TABLE}` u FORCE INDEX (PRIMARY) "
                f"WHERE {' AND '.join(where)} ORDER BY u.`{self.PK}` LIMIT %s", tuple(params))

    def ids_query(self, ids):
        if not ids:
            raise ValueError("IDs obrigatórios")
        fields = ", ".join(
            f"CAST(u.`{name}` AS CHAR)" if name in self.TEXT_DATES else f"u.`{name}`"
            for name in self.COLUMNS)
        marks = ", ".join(["%s"] * len(ids))
        return (f"SELECT {fields} FROM `{self.TABLE}` u FORCE INDEX (PRIMARY) "
                f"WHERE u.`{self.PK}` IN ({marks}) ORDER BY u.`{self.PK}`", tuple(ids))


usuario = UsuarioContract(
    TABLE="sa_usuario", TEXT_DATES=("dt_nascimento", "data_create"),
    FIELDS={
        "id_usuario": ("int(11)", "INTEGER", False),
        "ds_nome": ("varchar(50)", "VARCHAR(50)", False),
        "ds_sobrenome": ("varchar(50)", "VARCHAR(50)", True),
        "fl_sexo": ("char(1)", "VARCHAR(1)", True),
        "nr_documento": ("varchar(30)", "VARCHAR(30)", True),
        "dt_nascimento": ("date", "TEXT", True),
        "ds_email": ("varchar(150)", "VARCHAR(150)", True),
        "nr_telefone": ("varchar(20)", "VARCHAR(20)", True),
        "nr_celular": ("varchar(20)", "VARCHAR(20)", True),
        "ds_cep": ("varchar(10)", "VARCHAR(10)", True),
        "ds_endereco": ("varchar(100)", "VARCHAR(100)", True),
        "nr_numero": ("int(11)", "INTEGER", True),
        "ds_complemento": ("varchar(30)", "VARCHAR(30)", True),
        "ds_bairro": ("varchar(50)", "VARCHAR(50)", True),
        "id_cidade": ("int(11)", "INTEGER", True),
        "id_pais": ("varchar(11)", "VARCHAR(11)", True),
        "pelotao": ("varchar(50)", "VARCHAR(50)", True),
        "ds_categoria_balcao": ("enum", "TEXT", True),
        "nm_necessidades_especiais": ("varchar(3)", "VARCHAR(3)", True),
        "data_create": ("datetime", "TEXT", True),
        "data_update": ("timestamp", "TIMESTAMP", True),
    })

usuario_balcao = UsuarioContract(
    TABLE="sa_usuario_balcao", TEXT_DATES=("dt_nascimento", "dt_cadastro"),
    FIELDS={
        "id_usuario": ("int(10) unsigned", "BIGINT", False),
        "ds_nome": ("varchar(100)", "VARCHAR(100)", False),
        "fl_sexo": ("char(1)", "VARCHAR(1)", False),
        "nr_documento": ("varchar(45)", "VARCHAR(45)", False),
        "dt_nascimento": ("datetime", "TEXT", False),
        "ds_email": ("varchar(150)", "VARCHAR(150)", False),
        "ds_telefone": ("varchar(20)", "VARCHAR(20)", False),
        "ds_celular": ("varchar(20)", "VARCHAR(20)", False),
        "pelotao": ("varchar(45)", "VARCHAR(45)", False),
        "dt_cadastro": ("timestamp", "TEXT", True),
    })

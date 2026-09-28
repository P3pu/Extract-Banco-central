"""Contratos mínimos de pagamentos e transações Ativo, validados no MySQL."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FinanceiroContract:
    TABLE: str
    PK: str
    FIELDS: dict
    TEXT_DATES: tuple = ()
    RECON_DATES: tuple = ()
    INDEX_NAMES: dict | None = None

    @property
    def COLUMNS(self):
        return tuple(self.FIELDS)

    def validate_schema(self, columns, indexes):
        actual = {column["COLUMN_NAME"]: column for column in columns}
        for name, (mysql_type, _, nullable) in self.FIELDS.items():
            column = actual.get(name)
            if column is None or column["COLUMN_TYPE"].lower() != mysql_type:
                raise ValueError(f"Schema divergente: {self.TABLE}.{name}")
            if (column["IS_NULLABLE"] == "YES") != nullable:
                raise ValueError(f"Nullabilidade divergente: {self.TABLE}.{name}")
        if [item["COLUMN_NAME"] for item in indexes if item["INDEX_NAME"] == "PRIMARY"] != [self.PK]:
            raise ValueError(f"PK de {self.TABLE} divergente")
        required = self.RECON_DATES or ("id_pedido_pagamento",)
        for name in required:
            index_name = (self.INDEX_NAMES or {}).get(name, name)
            if not any(item["INDEX_NAME"] == index_name and item["COLUMN_NAME"] == name
                       and item["SEQ_IN_INDEX"] == 1
                       for item in indexes):
                raise ValueError(f"Índice {index_name} ausente em {self.TABLE}")

    def _select_fields(self):
        return ", ".join(
            f"CAST(t.`{name}` AS CHAR)" if name in self.TEXT_DATES else f"t.`{name}`"
            for name in self.COLUMNS)

    def page_query(self, batch_size, upper_id, cursor=None):
        if batch_size <= 0 or upper_id is None:
            raise ValueError("Lote ou limite inválido")
        where = [f"t.`{self.PK}` <= %s"]
        params = [upper_id]
        if cursor is not None:
            where.append(f"t.`{self.PK}` > %s")
            params.append(cursor)
        params.append(batch_size)
        return (f"SELECT {self._select_fields()} FROM `{self.TABLE}` t FORCE INDEX (PRIMARY) "
                f"WHERE {' AND '.join(where)} ORDER BY t.`{self.PK}` LIMIT %s", tuple(params))

    def reconcile_page_query(self, cutoff, upper_id, batch_size, cursor=None, date_column=None):
        if cutoff is None or upper_id is None or batch_size <= 0:
            raise ValueError("Janela, limite ou lote inválido")
        if self.RECON_DATES:
            if date_column not in self.RECON_DATES:
                raise ValueError("Coluna de reconciliação inválida")
            where = [f"t.`{date_column}` >= %s", f"t.`{self.PK}` <= %s"]
            params = [cutoff, upper_id]
            if cursor is not None:
                last_date, last_id = cursor
                where.append(f"(t.`{date_column}` > %s OR "
                             f"(t.`{date_column}` = %s AND t.`{self.PK}` > %s))")
                params.extend((last_date, last_date, last_id))
            params.append(batch_size)
            index_name = (self.INDEX_NAMES or {}).get(date_column, date_column)
            return (f"SELECT {self._select_fields()} FROM `{self.TABLE}` t "
                    f"FORCE INDEX (`{index_name}`) WHERE {' AND '.join(where)} "
                    f"ORDER BY t.`{date_column}`, t.`{self.PK}` LIMIT %s", tuple(params))
        if date_column is not None:
            raise ValueError("Coluna de reconciliação inválida")
        where = [f"t.`{self.PK}` <= %s",
                 "(t.`dt_cadastro` >= %s OR t.`dt_cancelamento_transacao` >= %s)"]
        params = [upper_id, cutoff, cutoff]
        if cursor is not None:
            where.append(f"t.`{self.PK}` > %s")
            params.append(cursor)
        params.append(batch_size)
        return (f"SELECT {self._select_fields()} FROM `{self.TABLE}` t FORCE INDEX (PRIMARY) "
                f"WHERE {' AND '.join(where)} ORDER BY t.`{self.PK}` LIMIT %s", tuple(params))


pedido_pagamento = FinanceiroContract(
    TABLE="sa_pedido_pagamento", PK="id_pedido_pagamento",
    FIELDS={
        "id_pedido_pagamento": ("int(11)", "INTEGER", False),
        "id_pedido": ("int(11)", "INTEGER", False),
        "id_formas_pagamento": ("int(11)", "INTEGER", False),
        "fl_status": ("enum('pendente','confirmado','recusado')", "VARCHAR(10)", False),
        "dt_registro": ("timestamp", "TIMESTAMP", False),
        "dt_pagamento": ("datetime", "TEXT", True),
    }, TEXT_DATES=("dt_pagamento",), RECON_DATES=("dt_registro", "dt_pagamento"),
    INDEX_NAMES={"dt_registro": "idx_dt_registro"})

transacao = FinanceiroContract(
    TABLE="sa_transacao", PK="id_transacao",
    FIELDS={
        "id_transacao": ("int(11)", "INTEGER", False),
        "id_pedido_pagamento": ("int(11)", "INTEGER", False),
        "nr_nsu": ("varchar(255)", "VARCHAR(255)", True),
        "nr_tid": ("varchar(255)", "VARCHAR(255)", True),
        "nr_codigo_autorizacao": ("varchar(255)", "VARCHAR(255)", True),
        "dt_cadastro": ("timestamp", "TIMESTAMP", False),
        "dt_cancelamento_transacao": ("datetime", "TIMESTAMP", True),
    })

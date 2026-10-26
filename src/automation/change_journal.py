"""Diário SQLite durável de IDs alterados, sem dados pessoais ou financeiros."""

import sqlite3
from pathlib import Path


class ChangeJournal:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS pending (
            origin TEXT NOT NULL, kind TEXT NOT NULL, source_id INTEGER NOT NULL,
            order_id INTEGER, PRIMARY KEY (origin, kind, source_id)
        )""")
        self.db.commit()

    def close(self):
        self.db.close()

    def record_rows(self, origin, entity, _batch_id, rows, columns):
        expected = {
            ("magento", "sales_order"): ("order", "entity_id", None),
            ("magento", "sales_order_item"): ("inscription", "item_id", "order_id"),
            ("ativo", "pedido"): ("order", "id_pedido", None),
            ("ativo", "pedido_evento"): ("inscription", "id_pedido_evento", "id_pedido"),
        }
        if (origin, entity) not in expected:
            raise ValueError("Entidade fora da automação RAW aprovada")
        kind, id_col, order_col = expected[(origin, entity)]
        id_index = columns.index(id_col)
        order_index = columns.index(order_col) if order_col else None
        parent_index = columns.index("parent_item_id") if entity == "sales_order_item" else None
        changes = []
        for row in rows:
            source_id = int(row[id_index])
            if parent_index is not None and row[parent_index] is not None:
                source_id = int(row[parent_index])
            order_id = int(row[order_index]) if order_index is not None and row[order_index] is not None else None
            if kind == "order":
                order_id = source_id
            changes.append((origin, kind, source_id, order_id))
        # Esta gravação ocorre antes do COMMIT RAW. Em falha, sobram apenas
        # reprocessamentos extras, nunca uma mudança RAW sem ID pendente.
        with self.db:
            self.db.executemany("""INSERT INTO pending(origin,kind,source_id,order_id)
                VALUES (?,?,?,?) ON CONFLICT(origin,kind,source_id)
                DO UPDATE SET order_id=excluded.order_id""", changes)

    def snapshot(self):
        return self.db.execute(
            "SELECT origin,kind,source_id,order_id FROM pending ORDER BY origin,kind,source_id"
        ).fetchall()

    def clear(self):
        with self.db:
            self.db.execute("DELETE FROM pending")

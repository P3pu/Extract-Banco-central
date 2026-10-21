"""Garantias estáticas do roteiro D5-A; nenhum banco é acessado."""

from pathlib import Path
import re

import pytest

from src.loaders.postgres_loader import _pg_type
from src.sources.ativo import pedido, pedido_evento
from src.sources.magento import sales_order, sales_order_item


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "sql/postgres/diagnostics/d5_a_catalog_readonly.sql"
CONTROLS = ROOT / "sql/postgres/diagnostics/d5_a_etl_controls_readonly.sql"


@pytest.mark.parametrize("path", [CATALOG, CONTROLS])
def test_diagnostic_sql_is_read_only_and_bounded(path):
    script = path.read_text(encoding="utf-8")
    executable = re.sub(r"--[^\n]*", "", script)
    assert executable.count("BEGIN READ ONLY;") == executable.count("COMMIT;")
    assert "SET LOCAL statement_timeout = '5s';" in executable
    assert "SET LOCAL lock_timeout = '500ms';" in executable
    assert not re.search(r"\b(?:INSERT|UPDATE|DELETE|TRUNCATE|CREATE|ALTER|DROP|COPY|DO|CALL|ANALYZE)\b",
                         executable, re.I)
    assert "current_database() = 'Atendimento'" in executable
    assert "current_setting('transaction_read_only') = 'on'" in executable


@pytest.mark.parametrize("table,contract", [
    ("magento_sales_order", sales_order),
    ("magento_sales_order_item", sales_order_item),
    ("ativo_pedido", pedido),
    ("ativo_pedido_evento", pedido_evento),
])
def test_sql_manifest_matches_versioned_source_contracts(table, contract):
    script = CATALOG.read_text(encoding="utf-8")
    match = re.search(r"\('" + table + r"', '([^']+)',\s*'([^']+)'\)", script)
    assert match is not None
    assert match.group(1) == contract.PK
    actual = match.group(2).split(",")
    expected = [f"{name}|{_pg_type(spec[1])[0]}|{_pg_type(spec[1])[1]}|"
                f"{str(not spec[2]).lower()}" for name, spec in contract.FIELDS.items()]
    assert actual == expected


def test_etl_run_queries_are_explain_only_pending_plan_review():
    script = CONTROLS.read_text(encoding="utf-8")
    assert script.count("EXPLAIN (FORMAT TEXT)") == 2
    assert "EXPLAIN ANALYZE" not in script
    assert "LIMIT 20;" in script
    assert "raw._etl_watermark" in script
    assert "('raw.ativo_pedido_evento', 'ativo', 'sa_pedido_evento')" in script

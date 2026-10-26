"""D4.1: contrato RAW e ausência de DDL permanente nas cargas autorizadas."""

import ast
from contextlib import contextmanager
from datetime import datetime
import importlib
import inspect
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.config.settings import Settings
from src.loaders import postgres_loader as loader
from src.pipeline import ativo_cupom, ativo_pedido, sales_order
from src.sources.ativo import pedido_evento
from src.sources.magento import sales_order as magento_order


class Result:
    def __init__(self, value):
        self.value = value

    def fetchall(self):
        return self.value

    def fetchone(self):
        return self.value


class CatalogConnection:
    def __init__(self, rows, pk):
        self.rows, self.pk = rows, pk
        self.queries = []

    def execute(self, query, params):
        self.queries.append((query, params))
        if "pg_catalog.pg_index" in query:
            return Result((self.pk,))
        if "pg_catalog.pg_class" in query:
            return Result(self.rows)
        raise AssertionError("Consulta inesperada no verificador")


def catalog_rows(contract):
    fields = {name: (sql_type, nullable)
              for name, (_, sql_type, nullable) in contract.FIELDS.items()}
    fields.update(loader.METADATA_FIELDS)
    return [("r", "p", name, *loader._pg_type(sql_type), not nullable, "", "")
            for name, (sql_type, nullable) in fields.items()]


@pytest.mark.parametrize("contract,target", [
    (magento_order, ("raw", "magento_sales_order")),
    (pedido_evento, ("raw", "ativo_pedido_evento")),
])
def test_catalog_contract_accepts_matching_permanent_table_without_ddl(contract, target):
    conn = CatalogConnection(catalog_rows(contract), [contract.PK])
    loader.validate_target(conn, target, contract)
    assert len(conn.queries) == 2
    assert all(query.lstrip().startswith("SELECT") for query, _ in conn.queries)
    assert all(params == target for _, params in conn.queries)


@pytest.mark.parametrize("drift", ["missing_table", "missing_column", "wrong_type",
                                         "wrong_nullability", "temporary_table", "wrong_pk"])
def test_catalog_contract_fails_closed_on_missing_or_incompatible_raw(drift):
    rows = catalog_rows(pedido_evento)
    pk = [pedido_evento.PK]
    if drift == "missing_table":
        rows = []
    elif drift == "missing_column":
        rows = [r for r in rows if r[2] != "fl_amigo"]
    elif drift == "wrong_type":
        rows = [r[:3] + ("bpchar", 5) + r[5:] if r[2] == "fl_amigo" else r for r in rows]
    elif drift == "wrong_nullability":
        rows = [r[:5] + (False,) + r[6:] if r[2] == "fl_amigo" else r for r in rows]
    elif drift == "temporary_table":
        rows = [(r[0], "t", *r[2:]) for r in rows]
    else:
        pk = ["id_pedido"]
    conn = CatalogConnection(rows, pk)
    with pytest.raises(ValueError, match="RAW"):
        loader.validate_target(conn, ("raw", "ativo_pedido_evento"), pedido_evento)
    assert all(query.lstrip().startswith("SELECT") for query, _ in conn.queries)


def test_magento_incremental_uses_existing_raw_and_keeps_upsert():
    conn, reader = MagicMock(), MagicMock()
    stamp = datetime(2026, 9, 28)
    reader.sales_order_bounds.return_value = (None, 10, stamp)
    row = [None] * len(magento_order.COLUMNS)
    row[0] = 10
    row[magento_order.COLUMNS.index("updated_at")] = stamp
    reader.sales_order_page.side_effect = [(tuple(row),), ()]
    progress = {"rows_extracted": 0, "rows_loaded": 0}
    with patch.object(loader, "validate_target") as validate, \
         patch.object(loader, "prepare") as prepare, \
         patch.object(loader, "upsert", return_value=1) as upsert:
        assert sales_order.load(conn, reader, "INCREMENTAL", 100, UUID(int=1),
                                stamp, progress) == stamp
    validate.assert_called_once_with(conn, ("raw", "magento_sales_order"), magento_order)
    prepare.assert_called_once_with(conn, ("raw", "magento_sales_order"))
    upsert.assert_called_once()
    conn.execute.assert_not_called()


@pytest.mark.parametrize("mode", ["INCREMENTAL", "RECONCILIATION"])
def test_ativo_pedido_evento_never_runs_migration_in_non_full_modes(mode):
    conn, reader = MagicMock(), MagicMock()
    reader.ativo_pedido_evento_bounds.return_value = (None, 100)
    reader.ativo_pedido_cutoff.return_value = datetime(2026, 9, 1)
    row = [None] * len(pedido_evento.COLUMNS)
    row[0] = 96
    reader.ativo_pedido_evento_page.side_effect = [(tuple(row),), ()]
    with patch.object(loader, "validate_target") as validate, \
         patch.object(loader, "prepare") as prepare, \
         patch.object(loader, "upsert", return_value=1) as upsert:
        newest = ativo_pedido.load(conn, reader, mode, 100, UUID(int=1), 95, 35,
                                   {"rows_extracted": 0, "rows_loaded": 0},
                                   entity="pedido_evento")
    assert newest == (96 if mode == "INCREMENTAL" else 95)
    validate.assert_called_once_with(conn, ("raw", "ativo_pedido_evento"), pedido_evento)
    prepare.assert_called_once_with(conn, ("raw", "ativo_pedido_evento"))
    upsert.assert_called_once()
    conn.execute.assert_not_called()


@pytest.mark.parametrize("pipeline,source,entity,old", [
    (sales_order, "magento", "sales_order", "2026-09-28T00:00:00"),
    (ativo_pedido, "ativo", "pedido_evento", "95"),
])
def test_schema_failure_rolls_back_business_and_never_advances_watermark(
        pipeline, source, entity, old):
    conn, reader = MagicMock(), MagicMock()
    conn.closed = False
    conn.execute.return_value.fetchone.side_effect = [(True,), (old,)]

    @contextmanager
    def pg(_):
        yield conn

    @contextmanager
    def mysql(*_):
        yield reader

    settings = MagicMock(spec=Settings)
    settings.batch_size, settings.reconciliation_days = 100, 35
    contract = pipeline.ENTITIES[entity][0]
    mode = "INCREMENTAL" if source == "magento" else "RECONCILIATION"
    with patch.object(pipeline.postgres, "connect", pg), \
         patch.object(pipeline.mysql, "connect", mysql), \
         patch.object(contract, "validate_schema"), \
         patch.object(loader, "validate_target", side_effect=ValueError("schema drift")), \
         patch.object(loader, "prepare") as prepare, \
         patch.object(loader, "upsert") as upsert:
        with pytest.raises(ValueError, match="schema drift"):
            pipeline.run(settings, mode, entity=entity)
    queries = [str(call.args[0]) for call in conn.execute.call_args_list]
    assert not any("INSERT INTO raw._etl_watermark" in query for query in queries)
    assert any("status='FAILED'" in query for query in queries)
    assert not any("CREATE TABLE" in query or "ALTER TABLE" in query for query in queries)
    assert conn.rollback.call_count == 1
    prepare.assert_not_called()
    upsert.assert_not_called()


def test_temp_stage_is_session_scoped_and_upsert_still_on_primary_key():
    prepare_source = inspect.getsource(loader.prepare)
    upsert_source = inspect.getsource(loader.upsert)
    assert "CREATE TEMP TABLE etl_raw_batch" in prepare_source
    assert "ON COMMIT DROP" in prepare_source
    assert "LIKE {} INCLUDING DEFAULTS" in prepare_source
    assert "TRUNCATE pg_temp.etl_raw_batch" in upsert_source
    assert "COPY pg_temp.etl_raw_batch" in upsert_source
    assert "ON CONFLICT ({}) DO UPDATE SET {}" in upsert_source


def test_full_remains_unavailable_through_executor_and_gates_remain_closed():
    from deploy.d1 import entrypoint
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    compose = (root / "deploy/d1/compose.yaml").read_text(encoding="utf-8")
    assert "D1_ENABLE_INCREMENTALS: ${D1_ENABLE_INCREMENTALS:-no}" in compose
    assert "D1_ENABLE_RECONCILIATION: ${D1_ENABLE_RECONCILIATION:-no}" in compose
    assert 'commands.add_parser("full")' not in inspect.getsource(entrypoint.main)


def test_cupom_reconciliation_has_no_permanent_ddl_path():
    source = inspect.getsource(ativo_cupom.run)
    assert "loader.validate_target(connection, TARGET, cupom)" in source
    assert "read_text" not in source
    assert "CREATE TABLE" not in source
    assert "ALTER TABLE" not in source


@pytest.mark.parametrize("module_name", [
    "sales_order", "ativo_pedido", "ativo_usuario", "ativo_financeiro",
    "ativo_complementos", "magento_company", "magento_company_user",
    "magento_customer_order_item", "magento_product_datetime",
    "magento_product_int", "magento_product_link",
    "magento_product_varchar", "magento_salesrule",
    "magento_salesrule_label",
])
def test_versioned_ddl_is_guarded_from_incremental_and_reconciliation(module_name):
    pipeline = importlib.import_module(f"src.pipeline.{module_name}")
    tree = ast.parse(inspect.getsource(pipeline.load))
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    ddl_reads = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "read_text"]
    assert ddl_reads, f"{module_name}: nenhum DDL localizado para verificar o gate"
    for node in ddl_reads:
        child = node
        guarded = False
        while child in parents:
            parent = parents[child]
            if isinstance(parent, ast.If):
                condition = ast.unparse(parent.test)
                guarded = (
                    (child in parent.body and condition in
                     {"mode == 'FULL'", "mode in {'FULL', 'SNAPSHOT'}"})
                    or (child in parent.orelse and condition == "mode == 'INCREMENTAL'")
                ) or guarded
            child = parent
        assert guarded, f"{module_name}: DDL acessível fora do ramo FULL/SNAPSHOT"


@pytest.mark.parametrize("name", [
    "company", "company_user", "customer_order_item", "product_datetime",
    "product_int", "product_link", "product_varchar", "salesrule",
    "salesrule_label",
])
def test_other_magento_incrementals_use_existing_raw_only(name):
    pipeline = importlib.import_module(f"src.pipeline.magento_{name}")
    contract = importlib.import_module(f"src.sources.magento.{name}")
    conn, reader = MagicMock(), MagicMock()
    getattr(reader, f"{name}_bounds").return_value = (None, None)
    with patch.object(loader, "validate_target") as validate, \
         patch.object(loader, "prepare") as prepare:
        pipeline.load(conn, reader, "INCREMENTAL", 100, UUID(int=1), 42,
                      {"rows_extracted": 0, "rows_loaded": 0})
    validate.assert_called_once_with(conn, pipeline.TARGET, contract)
    prepare.assert_called_once_with(conn, pipeline.TARGET)
    conn.execute.assert_not_called()


@pytest.mark.parametrize("module_name,entity,mode", [
    ("ativo_usuario", "usuario", "INCREMENTAL"),
    ("ativo_usuario", "usuario_balcao", "RECONCILIATION"),
    ("ativo_financeiro", "pedido_pagamento", "INCREMENTAL"),
    ("ativo_financeiro", "transacao", "RECONCILIATION"),
    ("ativo_complementos", "pedido_endereco", "INCREMENTAL"),
    ("ativo_complementos", "pedido_endereco", "RECONCILIATION"),
])
def test_other_ativo_incrementals_and_reconciliations_use_existing_raw_only(
        module_name, entity, mode):
    pipeline = importlib.import_module(f"src.pipeline.{module_name}")
    conn, reader = MagicMock(), MagicMock()
    reader.snapshot_bounds.return_value = (None, None)
    reader.ativo_pedido_evento_bounds.return_value = (None, None)
    contract = pipeline.ENTITIES[entity][0]
    target = ("raw", f"ativo_{entity}")
    with patch.object(loader, "validate_target") as validate, \
         patch.object(loader, "prepare") as prepare:
        pipeline.load(conn, reader, mode, 100, UUID(int=1), 42, 35,
                      {"rows_extracted": 0, "rows_loaded": 0}, entity)
    validate.assert_called_once_with(conn, target, contract)
    prepare.assert_called_once_with(conn, target)
    conn.execute.assert_not_called()

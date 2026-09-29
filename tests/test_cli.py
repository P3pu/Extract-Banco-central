from src.main import safe_error
from unittest.mock import patch
from src.main import main


def test_diagnostic_redacts_driver_payload():
    assert safe_error(Exception("Access denied for user secret password")) == "autenticação recusada"
    assert "secret" not in safe_error(Exception("unknown payload secret"))


def test_without_entity_runs_magento_tables():
    with patch("src.main.Settings.load"), patch("src.pipeline.sales_order.run") as run, \
         patch("src.pipeline.magento_product_varchar.run") as run_varchar:
        assert main(["incremental", "--source", "magento"]) == 0
    assert [c.kwargs["entity"] for c in run.call_args_list] == [
        "sales_order", "sales_order_item", "product"]
    assert run_varchar.call_args.args[1] == "INCREMENTAL"


def test_explicit_entity_runs_only_items():
    with patch("src.main.Settings.load"), patch("src.pipeline.sales_order.run") as run:
        assert main(["full", "--entity", "sales_order_item"]) == 0
    assert run.call_count == 1
    assert run.call_args.kwargs["entity"] == "sales_order_item"

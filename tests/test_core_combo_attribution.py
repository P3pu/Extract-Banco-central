from unittest.mock import MagicMock

from src.core import combo_attribution


def test_migrated_combo_rule_matches_one_to_one_by_order_and_event():
    sql = combo_attribution.SQL.read_text(encoding="utf-8")
    assert "p.protocolo ~ '^[0-9]{9}-[0-9]{1,2}$'" in sql
    assert "split_part(p.protocolo,'-',1)::bigint" in sql
    assert "substring(f.sku_inscricao_magento from '^(.*?COMBO[0-9]*)')" in sql
    assert "u.ativo_pedido=a.ativo_pedido AND u.evento_key=a.evento_key" in sql
    assert "WHERE p.por_inscricao=1 AND p.por_unidade=1" in sql
    # Combo do Magento entra como combo próprio; a inscrição oficial é a do Ativo.
    assert "INSERT INTO core.dim_combo (origem, combo_id_origem, nome_combo)" in sql
    assert "f.origem='ativo'" in sql
    assert "p.ativo_pedido::text || ':' || p.combo_sku grupo_comercial_id" in sql


def test_sync_skips_empty_scope_and_passes_all_flag():
    conn = MagicMock()
    assert combo_attribution.sync(conn) == 0
    conn.execute.assert_not_called()
    conn.execute.return_value.rowcount = 5
    assert combo_attribution.sync(conn, todos=True) == 5
    params = conn.execute.call_args.args[1]
    assert params["todos"] is True and params["ativo_pedidos"] == []
    assert params["validado_por"] and params["validado_em"].startswith("2026-10-30")


def test_sync_changed_uses_both_origins():
    conn = MagicMock()
    conn.execute.return_value.rowcount = 1
    combo_attribution.sync_changed(conn, {"ativo": {3, 1}, "magento": {9}})
    params = conn.execute.call_args.args[1]
    assert params["ativo_pedidos"] == [1, 3] and params["magento_pedidos"] == [9]
    assert params["todos"] is False

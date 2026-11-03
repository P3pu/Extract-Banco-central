from unittest.mock import MagicMock

from src.core import combo_attribution


def test_sync_skips_empty_scope_and_passes_all_flag():
    conn = MagicMock()
    assert combo_attribution.sync(conn) == 0
    conn.execute.assert_not_called()
    conn.execute.return_value.rowcount = 5
    assert combo_attribution.sync(conn, todos=True) == 5
    assert conn.execute.call_args.args[0] == combo_attribution.SQL.read_text(encoding="utf-8")
    params = conn.execute.call_args.args[1]
    assert params["todos"] is True and params["ativo_pedidos"] == []
    assert params["validado_por"] and params["validado_em"].startswith("2026-11-03")


def test_sync_changed_uses_only_ativo_orders():
    conn = MagicMock()
    conn.execute.return_value.rowcount = 1
    combo_attribution.sync_changed(conn, {"ativo": {3, 1}, "magento": {9}})
    params = conn.execute.call_args.args[1]
    assert params["ativo_pedidos"] == [1, 3] and "magento_pedidos" not in params
    assert params["todos"] is False
    conn = MagicMock()
    assert combo_attribution.sync_changed(conn, {"magento": {9}}) == 0
    conn.execute.assert_not_called()


def test_combo_rule_ignores_menu_and_keeps_one_combo_per_participant():
    sql = combo_attribution.SQL.read_text(encoding="utf-8")
    # O cardápio está incompleto: pertencem ao combo todas as inscrições, menos produtos.
    assert "staging." not in sql
    # Migrados seguem a mesma regra; atribuições da regra antiga por SKU saem.
    assert "fato_pedido" not in sql and "protocolo" not in sql
    assert "':ativo:'" in sql and "participante_id_origem" in sql
    # Hoodie e Mala tubo são eventos no Ativo, mas não são provas do combo.
    assert "x.evento_id_origem=e.evento_id_origem" in sql
    assert "x.evento_id_origem=f.evento_id_origem" in sql
    # Múltiplo exato do tamanho do combo_id separa combos do mesmo participante.
    assert "mode() WITHIN GROUP (ORDER BY qtd)" in sql
    assert "t.tamanho>=2 AND c.qtd>t.tamanho AND c.qtd %% t.tamanho=0" in sql
    assert "LIKE '%%:ativo:%%'" in sql and "LIKE '%%:%%COMBO%%'" in sql


def test_products_never_count_as_inscription():
    from src.core import runner
    seed = (combo_attribution._V1 / "008_evento_produto.sql").read_text(encoding="utf-8")
    assert combo_attribution._V1 / "008_evento_produto.sql" in runner.MIGRATIONS
    for evento in ("40006", "40007", "40103", "40186"):
        assert f"({evento}," in seed
    # Kit Vip fica em revisão, não na lista de produtos.
    assert "core.evento_revisao" in seed and "(33724," in seed
    ativo = (combo_attribution._V1 / "040_inscricao_ativo.sql").read_text(encoding="utf-8")
    assert "CASE WHEN produto THEN false" in ativo
    assert "'PRODUTO_NAO_INSCRICAO'" in ativo
    # Fora do hash: mudar a lista não recalcula a base inteira.
    assert "core.evento_produto" not in ativo.split("dep_hash", 1)[0].split("md5(ROW(", 1)[1]


def test_combo_vendido_view_avoids_double_counting():
    from src.core import runner
    view = (combo_attribution._V1 / "009_combo_vendido.sql").read_text(encoding="utf-8")
    assert combo_attribution._V1 / "009_combo_vendido.sql" in runner.MIGRATIONS
    assert "f.motivo_elegibilidade IS DISTINCT FROM 'COMBO_MIGRADO_ATIVO'" in view
    assert "GROUP BY a.grupo_comercial_id" in view
    # Magento: cada linha é uma prova; comprador + circuito + COMBO<n> formam o combo.
    assert "PARTITION BY l.comprador, l.circuito, l.provas, l.etapa" in view
    assert "COMBO([0-9]+)$" in view and "split_part(f.sku_inscricao_magento,'-',1)" in view
    assert "ATIVO_MIGRADO" not in view and "AS migrado_magento" in view
    # Combo em revisão não conta, e combo que já não contaria não vai para revisão.
    assert view.count("CASE WHEN r.motivo_revisao IS NOT NULL THEN FALSE ELSE r.contabiliza END") == 2
    assert "CASE WHEN a.contabiliza IS NOT FALSE THEN NULLIF(concat_ws" in view
    assert "CASE WHEN g.contabiliza IS NOT FALSE THEN NULLIF(concat_ws" in view
    for motivo in ("TAMANHO", "VALOR", "PRODUTO", "SEM_NUMERO", "ETAPAS_INCOMPLETAS", "SEM_COMPRADOR"):
        assert f"'{motivo}'" in view
    # Combo vendido conta mesmo com uma prova cancelada.
    assert "CASE WHEN BOOL_OR(f.contabiliza_inscricao IS TRUE) THEN TRUE" in view
    # O valor das provas canceladas não entra no combo.
    assert view.count("FILTER (WHERE f.flag_cancelado_inscricao IS NOT TRUE)") == 4
    assert view.count("FILTER (WHERE o.flag_cancelado_inscricao IS NOT TRUE)") == 3

"""Aplica views STAGING por fase, sem modificar tabelas RAW."""

import argparse

from src.config.settings import ROOT, Settings
from src.db.postgres import connect


PHASES = {
    1: ("001_create_staging_schema.sql",),
    2: tuple(f"magento/{name}" for name in (
        "010_magento_option_label.sql", "020_magento_pedido.sql",
        "030_magento_item_pedido.sql", "040_magento_produto.sql")),
    3: tuple(f"magento/{name}" for name in (
        "050_magento_produto_evento_mapeamento.sql", "060_magento_evento.sql",
        "070_magento_cliente.sql", "080_magento_endereco_cliente.sql",
        "090_magento_item_cliente.sql", "100_magento_cliente_empresa.sql")),
    4: tuple(f"magento/{name}" for name in (
        "110_magento_pedido_regra.sql", "120_magento_bundle_componente.sql",
        "130_magento_inscricao.sql")),
    5: tuple(f"ativo/{name}" for name in (
        "200_ativo_pedido.sql", "210_ativo_evento.sql",
        "220_ativo_modalidade.sql", "230_ativo_categoria.sql",
        "240_ativo_tamanho_camiseta.sql")),
    6: tuple(f"ativo/{name}" for name in (
        "250_ativo_usuario.sql", "260_ativo_usuario_balcao.sql",
        "270_ativo_forma_pagamento.sql", "280_ativo_pagamento.sql",
        "290_ativo_transacao.sql", "300_ativo_pedido_produto.sql",
        "310_ativo_endereco_pedido.sql", "320_ativo_cidade.sql",
        "330_ativo_estado.sql", "340_ativo_pais.sql",
        "350_ativo_combo.sql", "360_ativo_cupom.sql",
        "365_ativo_cupom_desconto.sql")),
    7: ("ativo/370_ativo_inscricao.sql",),
}


def deploy_phase(settings, phase):
    root = ROOT / "sql" / "staging"
    # A conexão confirma que o database é Atendimento. Cada fase é atômica.
    with connect(settings) as connection:
        for relative_path in PHASES[phase]:
            sql_path = root / relative_path
            connection.execute(sql_path.read_text(encoding="utf-8"))
    print(f"Fase {phase}: {len(PHASES[phase])} script(s) aplicado(s)")


def main():
    parser = argparse.ArgumentParser(description="Implanta views STAGING em Atendimento")
    parser.add_argument("--phase", type=int, choices=PHASES, required=True)
    args = parser.parse_args()
    settings = Settings.load()
    deploy_phase(settings, args.phase)


if __name__ == "__main__":
    main()

-- Produtos do combo (Hoodie, Mala tubo, Óculos, Moletom) são eventos no Ativo,
-- sem campo que os identifique (decisão 03/11/2026): não contam como inscrição
-- nem como prova de combo. Curadoria manual: produto novo entra nesta lista.
CREATE TABLE IF NOT EXISTS core.evento_produto (
    evento_id_origem BIGINT PRIMARY KEY,
    nome_produto TEXT NOT NULL CHECK (BTRIM(nome_produto)<>'')
);

INSERT INTO core.evento_produto (evento_id_origem, nome_produto) VALUES
    (40006,'Hoodie 2026'),
    (40007,'Mala tubo 2026'),
    (40024,'Hoodie 2026 - Aracaju'),
    (40025,'Mala tubo 2026 - Aracaju'),
    (40032,'Mala tubo 2026 - João Pessoa'),
    (40037,'Mala tubo 2026 - Natal'),
    (40042,'Hoodie 2026 - TR Crono'),
    (40087,'Mala tubo 2026 - Cuiabá'),
    (40090,'Hoodie 2026 - Cuiabá'),
    (40103,'Moletom Bravus'),
    (40186,'Óculos')
ON CONFLICT (evento_id_origem) DO NOTHING;

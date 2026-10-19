-- PROPOSTA DE DEPENDÊNCIAS, NÃO EXECUTAR. NÃO É MIGRAÇÃO APROVADA.
-- Validar no information_schema MySQL tipo, nulabilidade, PK e volume de cada
-- coluna antes de versionar estas instruções em sql/postgres e src/sources.
-- A Fase A comprovou os nomes/relacionamentos abaixo, não todos os tipos.

-- Cupom cabeçalho (sa_cupom_desconto). Incluir somente colunas validadas;
-- a extração deverá buscar PKs referenciadas por ativo_cupom_desconto_item e
-- reconciliar alterações históricas, não apenas id crescente.
CREATE TABLE raw.ativo_cupom_desconto (
    id_cupom_desconto BIGINT PRIMARY KEY,
    en_cupom_classificacao TEXT,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
CREATE VIEW staging.ativo_cupom_desconto AS
SELECT id_cupom_desconto AS cupom_desconto_id,
       NULLIF(BTRIM(en_cupom_classificacao), '') AS classificacao,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_cupom_desconto;

-- Status detalhado: validar tipo/semântica em especial dos códigos com
-- tipo='pedido'. Não converter código 17 automaticamente para pago.
CREATE TABLE raw.ativo_status_detalhado (
    id_status_detalhado INTEGER PRIMARY KEY,
    id_pedido_status INTEGER,
    status TEXT,
    tipo TEXT,
    ativo TEXT,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);
CREATE VIEW staging.ativo_status_detalhado AS
SELECT id_status_detalhado AS status_detalhado_id,
       id_pedido_status AS status_pedido_id,
       status AS descricao, tipo, ativo,
       _source AS origem, _extracted_at AS extraido_em, _batch_id AS batch_id
FROM raw.ativo_status_detalhado;

-- Comprador do pedido Ativo: preencher por sa_pedido.id_usuario na mesma
-- extração/reconciliação do pedido. O DDL isolado deixa dados antigos NULL.
ALTER TABLE raw.ativo_pedido ADD COLUMN id_usuario BIGINT;
-- Atualizar staging.ativo_pedido para expor p.id_usuario AS comprador_usuario_id.
-- Não usar inscricao.usuario_id como substituto.

-- Combo: o campo foi encontrado em MySQL mas seu domínio ainda exige auditoria.
ALTER TABLE raw.ativo_combo ADD COLUMN nr_qntprovas INTEGER;
-- Atualizar staging.ativo_combo para expor nr_qntprovas sem convertê-lo
-- automaticamente em qtd_inscricoes_previstas quando 0 ou divergente.

-- sa_combo_evento_categoria: NÃO há DDL até obter PK física, tipos completos,
-- chave de histórico e semântica das linhas opcionais/fl_obrigatorio.
-- Depois da validação, criar RAW + view 1:1 e reconciliar por PK, com teste de
-- composição evento/categoria antes de ativar flag_composicao_validada.

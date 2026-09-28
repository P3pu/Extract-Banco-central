-- dt_evento/dt_modificacao: TEXT preserva as datas zero presentes na origem.
CREATE TABLE IF NOT EXISTS raw.ativo_evento (
    id_evento INTEGER PRIMARY KEY,
    id_campanha_salesforce VARCHAR(50),
    ds_evento VARCHAR(100) NOT NULL,
    dt_evento TEXT,
    hr_evento VARCHAR(20),
    id_pais_origem INTEGER,
    data_update TIMESTAMP,
    dt_modificacao TEXT,
    _source TEXT NOT NULL,
    _extracted_at TIMESTAMPTZ NOT NULL,
    _batch_id UUID NOT NULL
);

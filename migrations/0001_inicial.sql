CREATE TABLE categorias (
    slug TEXT PRIMARY KEY,
    nome TEXT NOT NULL
);

INSERT INTO categorias (slug, nome) VALUES
    ('lugar', 'Lugares'),
    ('produto', 'Produtos');

CREATE TABLE itens (
    id INTEGER PRIMARY KEY,
    categoria TEXT NOT NULL REFERENCES categorias(slug),
    nome TEXT NOT NULL CHECK (length(trim(nome)) > 0),
    descricao TEXT NOT NULL DEFAULT '',
    detalhes TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(detalhes) AND json_type(detalhes) = 'object'),
    criado_em TEXT NOT NULL
);

CREATE TABLE experiencias (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES itens(id) ON DELETE CASCADE,
    data TEXT NOT NULL,
    -- NULL é não avaliado. Zero é uma avaliação válida.
    nota REAL CHECK (nota IN (0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5)),
    texto TEXT NOT NULL DEFAULT '',
    pedido TEXT NOT NULL DEFAULT '',
    preco_centavos INTEGER CHECK (
        typeof(preco_centavos) = 'integer' AND preco_centavos >= 0
        OR preco_centavos IS NULL
    ),
    repetiria INTEGER CHECK (repetiria IN (0, 1)),
    criado_em TEXT NOT NULL
);

CREATE TABLE tags_experiencia (
    experiencia_id INTEGER NOT NULL REFERENCES experiencias(id) ON DELETE CASCADE,
    tag TEXT NOT NULL CHECK (length(trim(tag)) > 0),
    PRIMARY KEY (experiencia_id, tag)
);

CREATE TABLE fotos (
    id INTEGER PRIMARY KEY,
    experiencia_id INTEGER NOT NULL REFERENCES experiencias(id) ON DELETE CASCADE,
    chave_r2 TEXT NOT NULL UNIQUE,
    tipo_mime TEXT NOT NULL,
    tamanho_bytes INTEGER NOT NULL CHECK (tamanho_bytes > 0),
    ordem INTEGER NOT NULL DEFAULT 0 CHECK (ordem >= 0)
);

CREATE INDEX idx_itens_categoria ON itens(categoria);
CREATE INDEX idx_experiencias_timeline ON experiencias(item_id, data DESC, id DESC);
CREATE INDEX idx_fotos_experiencia ON fotos(experiencia_id, ordem);

-- Índice derivado: rowid será o id do item. Escritas sincronizadas no incremento 2.
CREATE VIRTUAL TABLE busca_itens USING fts5(
    nome,
    descricao,
    localizacao,
    detalhes,
    relatos,
    pedidos,
    tags,
    tokenize = 'unicode61 remove_diacritics 2'
);

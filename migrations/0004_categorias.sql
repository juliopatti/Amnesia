-- Novas categorias raiz. Nomes, ordem e campos ficam em CATEGORIAS (src/dominio.py);
-- esta tabela só garante que o slug de cada item existe.
-- Subcategorias futuras usam o slug da raiz como prefixo: 'musica.rock'.
INSERT INTO categorias (slug, nome) VALUES
    ('restaurante', 'Bares e restaurantes'),
    ('filme', 'Filmes'),
    ('serie', 'Séries'),
    ('livro', 'Livros'),
    ('musica', 'Música');

-- Até aqui "lugar" era usado para bares e restaurantes; agora significa cidade,
-- turismo e afins. Os campos são os mesmos, então os detalhes não mudam.
UPDATE itens SET categoria = 'restaurante' WHERE categoria = 'lugar';

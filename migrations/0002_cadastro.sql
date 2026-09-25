-- A mesma chave reapresentada pelo formulário recupera o primeiro registro.
ALTER TABLE itens ADD COLUMN chave_criacao TEXT;
CREATE UNIQUE INDEX idx_itens_chave_criacao ON itens(chave_criacao);
ALTER TABLE experiencias ADD COLUMN chave_envio TEXT;
CREATE UNIQUE INDEX idx_experiencias_chave_envio ON experiencias(chave_envio);

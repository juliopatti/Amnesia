-- Tentativas de login com senha errada, para bloquear por alguns minutos depois de
-- muitas seguidas. Linhas antigas são apagadas a cada nova falha; um acerto limpa tudo.
CREATE TABLE falhas_login (
    id INTEGER PRIMARY KEY,
    instante TEXT NOT NULL
);
CREATE INDEX idx_falhas_login_instante ON falhas_login(instante);

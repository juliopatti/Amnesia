"""Dublês sem rede para o serviço e o binding D1."""


class ArmazenamentoMemoria:
    async def listar_categorias(self):
        return [{"slug": "lugar", "nome": "Lugares"}]

    async def contar_registros(self):
        return {"itens": 2, "experiencias": 3, "documentos_busca": 2}


class BancoD1:
    def __init__(self, linhas):
        self.linhas = linhas
        self.sql = None
        self.parametros = ()

    def prepare(self, sql):
        self.sql = sql
        return self

    def bind(self, *parametros):
        self.parametros = parametros
        return self

    async def all(self):
        return {"results": self.linhas, "success": True}


class BancoSQLite:
    """Executa o SQL real e reproduz o contrato transacional de D1.batch."""
    def __init__(self):
        from pathlib import Path
        import sqlite3
        self.conexao = sqlite3.connect(':memory:', isolation_level=None)
        self.conexao.row_factory = sqlite3.Row
        self.conexao.execute('PRAGMA foreign_keys = ON')
        for migracao in sorted((Path(__file__).resolve().parents[1] / 'migrations').glob('*.sql')):
            self.conexao.executescript(migracao.read_text())
        self.falhar_em = None

    def prepare(self, sql):
        return ComandoSQLite(self, sql)

    async def batch(self, comandos):
        self.conexao.execute('BEGIN')
        try:
            resultados = [await comando.all() for comando in comandos]
            self.conexao.execute('COMMIT')
            return resultados
        except Exception:
            self.conexao.execute('ROLLBACK')
            raise


class ComandoSQLite:
    def __init__(self, banco, sql, parametros=()):
        self.banco, self.sql, self.parametros = banco, sql, parametros

    def bind(self, *parametros):
        return ComandoSQLite(self.banco, self.sql, parametros)

    async def all(self):
        if self.banco.falhar_em and self.banco.falhar_em in self.sql:
            raise RuntimeError('Falha de banco simulada')
        cursor = self.banco.conexao.execute(self.sql, self.parametros)
        return {'results': [dict(linha) for linha in cursor.fetchall()], 'success': True}


class ArquivosMemoria:
    def __init__(self):
        self.arquivos = {}
        self.falhar = False
        self.falhar_exclusao = False

    async def salvar(self, chave, conteudo):
        if self.falhar:
            raise OSError('Falha de upload simulada')
        self.arquivos[chave] = conteudo

    async def excluir(self, chave):
        if self.falhar_exclusao:
            raise OSError('Falha de exclusão simulada')
        self.arquivos.pop(chave, None)

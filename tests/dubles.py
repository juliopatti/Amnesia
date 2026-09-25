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

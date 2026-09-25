"""Adaptador D1. O domínio não depende dos objetos JavaScript deste binding."""


class ArmazenamentoD1:
    def __init__(self, banco):
        self.banco = banco

    async def consultar(self, sql, parametros=()):
        comando = self.banco.prepare(sql)
        if parametros:
            comando = comando.bind(*parametros)
        resultado = await comando.all()
        # A SDK atual já converte o resultado do binding em dict/list.
        return [dict(linha) for linha in resultado["results"]]

    async def listar_categorias(self):
        return await self.consultar("SELECT slug, nome FROM categorias ORDER BY nome")

    async def contar_registros(self):
        linhas = await self.consultar("""
            SELECT (SELECT count(*) FROM itens) AS itens,
                   (SELECT count(*) FROM experiencias) AS experiencias,
                   (SELECT count(*) FROM busca_itens) AS documentos_busca
        """)
        return linhas[0]

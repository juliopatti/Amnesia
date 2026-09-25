from datetime import datetime, timezone
from urllib.parse import urlsplit

from workers import Response, WorkerEntrypoint

from armazenamento import ArmazenamentoD1
from paginas import pagina_inicial
from servicos import verificar_base


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        caminho = urlsplit(request.url).path
        cabecalhos = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if request.method != "GET":
            return Response("Método não permitido.", status=405,
                            headers={**cabecalhos, "Allow": "GET"})
        if caminho not in ("/", "/saude"):
            return Response("Essa lembrança não está aqui.", status=404, headers=cabecalhos)
        try:
            resumo = await verificar_base(ArmazenamentoD1(self.env.DB), datetime.now(timezone.utc))
        except Exception as erro:
            print("Falha ao verificar a base:", repr(erro))
            return Response("Base indisponível. Confira as migrações no README.",
                            status=503, headers=cabecalhos)
        if caminho == "/saude":
            return Response.json(resumo, headers=cabecalhos)
        return Response(pagina_inicial(resumo["categorias"]),
                        headers={**cabecalhos, "Content-Type": "text/html; charset=utf-8"})

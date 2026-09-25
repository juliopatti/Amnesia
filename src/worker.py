"""Fronteira HTTP: origem, limites, formulários e respostas. Regras ficam nos serviços."""

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from workers import Response, WorkerEntrypoint

from armazenamento import ArmazenamentoD1, ArmazenamentoR2
from dominio import CAMPOS_CATEGORIA, MAX_BUSCA, MAX_FOTO_BYTES, horario_local, preco_em_centavos
from paginas import pagina_inicial, formulario, confirmacao, item_guardado
from servicos import verificar_base, buscar, criar_item, registrar_experiencia, anexar_foto


CABECALHOS = {
    "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
}


def html(conteudo, status=200):
    return Response(conteudo, status=status, headers={**CABECALHOS, "Content-Type": "text/html; charset=utf-8"})


def resposta_json(conteudo, status=200):
    return Response.from_json(conteudo, status=status, headers=CABECALHOS)


def redirecionar(url):
    return Response("", status=303, headers={**CABECALHOS, "Location": url})


def identificador(valor):
    if not isinstance(valor, str) or not valor.isascii() or not valor.isdigit() or len(valor) > 15 or int(valor) <= 0:
        raise ValueError("Identificador inválido.")
    return int(valor)


def origem_permitida(request):
    destino = urlsplit(request.url)
    origem = request.headers.get("Origin", "")
    return (origem == f"{destino.scheme}://{destino.netloc}"
            and request.headers.get("Sec-Fetch-Site", "") not in ("cross-site", "none"))


async def ler_corpo(request, limite):
    tamanho = request.headers.get("Content-Length")
    if tamanho and (not tamanho.isdigit() or int(tamanho) > limite):
        raise ValueError("O envio ultrapassou o tamanho permitido.")
    if request.body is None:
        return b""
    leitor = request.body.getReader()
    partes, total = [], 0
    try:
        while True:
            parte = await leitor.read()
            if parte.done:
                break
            dados = parte.value.to_bytes()
            total += len(dados)
            if total > limite:
                await leitor.cancel()
                raise ValueError("O envio ultrapassou o tamanho permitido.")
            partes.append(dados)
    finally:
        leitor.releaseLock()
    return b"".join(partes)


def dados_item(valores):
    categoria = valores.get("categoria", "lugar")
    return {"nome": valores.get("nome", ""), "categoria": categoria,
            "descricao": valores.get("descricao", ""),
            "detalhes": {campo: valores.get(campo, "") for campo in CAMPOS_CATEGORIA.get(categoria, ())}}


class Default(WorkerEntrypoint):
    async def pagina_busca(self, banco, consulta):
        criterios = {campo: consulta.get(parametro, [""])[0] for campo, parametro in
                     (("texto", "q"), ("categoria", "categoria"), ("nota_min", "nota_min"), ("nota_max", "nota_max"))}
        categorias = await banco.listar_categorias()
        try:
            pagina = identificador(consulta.get("pagina", ["1"])[0])
            return html(pagina_inicial(categorias, await buscar(banco, criterios, pagina), pagina))
        except ValueError as erro:
            # Mantém o texto digitado no campo; filtros inválidos voltam ao padrão.
            eco = {"busca": {"texto": criterios["texto"][:MAX_BUSCA], "categoria": "",
                             "nota_min": None, "nota_max": None}, "itens": [], "tem_mais": False}
            return html(pagina_inicial(categorias, eco, erro=str(erro)), 422)

    async def fetch(self, request):
        url = urlsplit(request.url)
        caminho = url.path
        banco = ArmazenamentoD1(self.env.DB)
        instante = datetime.now(timezone.utc)
        if request.method not in ("GET", "POST"):
            return Response("Método não permitido.", status=405, headers={**CABECALHOS, "Allow": "GET, POST"})
        if request.method == "POST" and not origem_permitida(request):
            return resposta_json({"erro": "Envio recusado: abra o formulário neste site."}, 403)
        try:
            if request.method == "GET":
                if caminho in ("/estilo.css", "/fotos.js", "/htmx.min.js"):
                    return await self.env.ASSETS.fetch(request)
                consulta = parse_qs(url.query)
                if caminho == "/saude":
                    return resposta_json(await verificar_base(banco, instante))
                if caminho == "/":
                    return await self.pagina_busca(banco, consulta)
                if caminho == "/registrar":
                    item = None
                    if consulta.get("item_id"):
                        item = await banco.obter_item(identificador(consulta["item_id"][0]))
                        if not item:
                            raise LookupError("Esse item não foi encontrado.")
                    return html(formulario(horario_local(instante)[:10], uuid4().hex, item))
                if caminho.startswith("/experiencias/"):
                    experiencia = await banco.obter_experiencia(identificador(caminho.removeprefix("/experiencias/")))
                    if not experiencia:
                        raise LookupError("Essa experiência não foi encontrada.")
                    return html(confirmacao(experiencia, await banco.listar_fotos(experiencia["id"])))
                if caminho.startswith("/itens/"):
                    item = await banco.obter_item(identificador(caminho.removeprefix("/itens/")))
                    if not item:
                        raise LookupError("Esse item não foi encontrado.")
                    return html(item_guardado(item))
                if caminho.startswith("/fotos/"):
                    foto = await banco.obter_foto(identificador(caminho.removeprefix("/fotos/")))
                    objeto = await ArmazenamentoR2(self.env.FOTOS).obter(foto["chave_r2"]) if foto else None
                    if objeto is None:
                        raise LookupError("Essa foto não foi encontrada.")
                    return Response(objeto.body, headers={**CABECALHOS, "Content-Type": "image/jpeg"})
            elif caminho == "/registros":
                if request.headers.get("Content-Type", "").split(";")[0] != "application/x-www-form-urlencoded":
                    return resposta_json({"erro": "Formato de formulário não suportado."}, 415)
                conteudo = (await ler_corpo(request, 64 * 1024)).decode("utf-8")
                campos = parse_qs(conteudo, keep_blank_values=True, max_num_fields=40)
                if any(len(valores) != 1 for valores in campos.values()):
                    raise ValueError("O formulário contém campos repetidos.")
                valores = {campo: valores[0] for campo, valores in campos.items()}
                quer_json = "application/json" in request.headers.get("Accept", "")
                item_id = identificador(valores["item_id"]) if valores.get("item_id") else None
                try:
                    chave = valores.get("chave", "")
                    if valores.get("acao") == "item" and item_id is None:
                        salvo = await criar_item(banco, dados_item(valores), chave, instante)
                        destino = {"url": f"/itens/{salvo}", "item_id": salvo}
                    else:
                        if valores.get("acao", "experiencia") != "experiencia":
                            raise ValueError("Ação desconhecida.")
                        resposta = valores.get("repetiria", "")
                        if resposta not in ("", "sim", "nao"):
                            raise ValueError("Escolha sim, não ou deixe sem resposta.")
                        dados = {"data": valores.get("data"), "nota": valores.get("nota"),
                                 "texto": valores.get("texto", ""), "pedido": valores.get("pedido", ""),
                                 "preco_centavos": preco_em_centavos(valores.get("preco", "")),
                                 "repetiria": {"": None, "sim": True, "nao": False}[resposta],
                                 "tags": [t for t in valores.get("tags", "").split(",") if t.strip()]}
                        salvo = await registrar_experiencia(banco, dados, chave, instante,
                            item_id=item_id, novo_item=dados_item(valores) if item_id is None else None)
                        destino = {"url": f"/experiencias/{salvo['id']}", "experiencia_id": salvo["id"], "item_id": salvo["item_id"]}
                    return resposta_json(destino) if quer_json else redirecionar(destino["url"])
                except ValueError as erro:
                    if quer_json:
                        return resposta_json({"erro": str(erro)}, 422)
                    item = await banco.obter_item(item_id) if item_id else None
                    return html(formulario(horario_local(instante)[:10], valores.get("chave", ""), item, valores, str(erro)), 422)
            elif caminho.startswith("/uploads/"):
                experiencia_id = identificador(caminho.removeprefix("/uploads/"))
                conteudo = await ler_corpo(request, MAX_FOTO_BYTES)
                foto = await anexar_foto(banco, ArmazenamentoR2(self.env.FOTOS), experiencia_id,
                    request.headers.get("X-Chave-Foto", ""), conteudo, request.headers.get("Content-Type", ""))
                return resposta_json({"id": foto["id"], "url": f"/fotos/{foto['id']}"})
        except LookupError as erro:
            return resposta_json({"erro": str(erro)}, 404)
        except ValueError as erro:
            return resposta_json({"erro": str(erro)}, 400)
        except Exception as erro:
            # Mensagens do binding podem conter SQL/dados pessoais: registrar só o tipo.
            print("Falha na operação:", type(erro).__name__)
            return resposta_json({"erro": "Não foi possível concluir. Tente novamente; o mesmo envio não duplica o registro."}, 503)
        return Response("Essa lembrança não está aqui.", status=404, headers=CABECALHOS)

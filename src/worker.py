"""Fronteira HTTP: origem, limites, formulários e respostas. Regras ficam nos serviços."""

from datetime import datetime, timezone
import re
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from workers import Response, WorkerEntrypoint

from armazenamento import ArmazenamentoD1, ArmazenamentoR2
from dominio import CAMPOS_CATEGORIA, MAX_BUSCA, MAX_FOTO_BYTES, horario_local, preco_em_centavos
from paginas import (pagina_inicial, formulario, confirmacao, pagina_item, formulario_item,
                     formulario_experiencia, confirmar_exclusao, valores_item, valores_experiencia)
from servicos import (verificar_base, buscar, criar_item, registrar_experiencia, anexar_foto,
                      editar_item, editar_experiencia, excluir_experiencia, excluir_foto)


RECURSO = re.compile(r"/(itens|experiencias|fotos)/([^/]+)(?:/(editar|excluir))?")
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


def dados_experiencia(valores):
    resposta = valores.get("voltaria", "")
    if resposta not in ("", "0", "1", "2", "3", "4", "5"):
        raise ValueError("Escolha uma das respostas de “Voltaria?” ou deixe sem resposta.")
    return {"data": valores.get("data"), "nota": valores.get("nota"),
            "texto": valores.get("texto", ""), "pedido": valores.get("pedido", ""),
            "preco_centavos": preco_em_centavos(valores.get("preco", "")),
            "voltaria": int(resposta) if resposta else None,
            "tags": [t for t in valores.get("tags", "").split(",") if t.strip()]}


async def ler_formulario(request):
    """Retorna None para formatos diferentes de formulário simples; a rota responde 415."""
    if request.headers.get("Content-Type", "").split(";")[0] != "application/x-www-form-urlencoded":
        return None
    conteudo = (await ler_corpo(request, 64 * 1024)).decode("utf-8")
    campos = parse_qs(conteudo, keep_blank_values=True, max_num_fields=40)
    if any(len(valores) != 1 for valores in campos.values()):
        raise ValueError("O formulário contém campos repetidos.")
    return {campo: valores[0] for campo, valores in campos.items()}


FORMATO_RECUSADO = {"erro": "Formato de formulário não suportado."}


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

    async def recurso(self, request, banco, instante, tipo, texto_id, acao):
        """Páginas, edição e exclusão de itens, experiências e fotos. None significa rota inexistente."""
        registro_id = identificador(texto_id)
        arquivos = ArmazenamentoR2(self.env.FOTOS)
        valores = None
        if request.method == "POST":
            if acao is None:
                return None
            valores = await ler_formulario(request)
            if valores is None:
                return resposta_json(FORMATO_RECUSADO, 415)
        if tipo == "itens":
            item = await banco.obter_item(registro_id)
            if not item:
                raise LookupError("Esse item não foi encontrado.")
            if acao is None:
                return html(pagina_item(item, await banco.listar_experiencias(registro_id)))
            if acao != "editar":
                return None
            if valores is None:
                return html(formulario_item(item, valores_item(item)))
            try:
                await editar_item(banco, registro_id, dados_item(valores))
            except ValueError as erro:
                return html(formulario_item(item, {"categoria": item["categoria"], **valores}, str(erro)), 422)
            return redirecionar(f"/itens/{registro_id}")
        if tipo == "experiencias":
            experiencia = await banco.obter_experiencia(registro_id)
            if not experiencia:
                raise LookupError("Essa experiência não foi encontrada.")
            if acao is None:
                return html(confirmacao(experiencia, await banco.listar_fotos(registro_id)))
            if acao == "editar" and valores is None:
                tags = await banco.listar_tags(registro_id)
                return html(formulario_experiencia(experiencia, valores_experiencia(experiencia, tags)))
            if acao == "editar":
                try:
                    await editar_experiencia(banco, registro_id, dados_experiencia(valores), instante)
                except ValueError as erro:
                    return html(formulario_experiencia(experiencia, valores, str(erro)), 422)
                return redirecionar(f"/experiencias/{registro_id}")
            if valores is None:
                return html(confirmar_exclusao(
                    "Excluir esta experiência?",
                    f"{experiencia['data']} em {experiencia['nome']}. Relato, tags e fotos vão embora juntos.",
                    f"/experiencias/{registro_id}/excluir", f"/experiencias/{registro_id}"))
            resultado = await excluir_experiencia(banco, arquivos, registro_id)
            if resultado["orfaos"]:
                print("Fotos não removidas do R2:", resultado["orfaos"])
            return redirecionar(f"/itens/{resultado['item_id']}")
        foto = await banco.obter_foto(registro_id)
        if not foto:
            raise LookupError("Essa foto não foi encontrada.")
        if acao is None:
            objeto = await arquivos.obter(foto["chave_r2"])
            if objeto is None:
                raise LookupError("Essa foto não foi encontrada.")
            return Response(objeto.body, headers={**CABECALHOS, "Content-Type": "image/jpeg"})
        if acao != "excluir":
            return None
        if valores is None:
            previa = f'<img class="previa-exclusao" src="/fotos/{registro_id}" alt="Foto que será removida">'
            return html(confirmar_exclusao("Remover esta foto?", "A experiência continua; só a foto sai.",
                f"/fotos/{registro_id}/excluir", f"/experiencias/{foto['experiencia_id']}", previa))
        resultado = await excluir_foto(banco, arquivos, registro_id)
        if resultado["orfaos"]:
            print("Foto não removida do R2:", resultado["orfaos"])
        return redirecionar(f"/experiencias/{resultado['experiencia_id']}")

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
            if encontrado := RECURSO.fullmatch(caminho):
                resposta = await self.recurso(request, banco, instante, *encontrado.groups())
                if resposta is not None:
                    return resposta
            elif request.method == "GET":
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
            elif caminho == "/registros":
                valores = await ler_formulario(request)
                if valores is None:
                    return resposta_json(FORMATO_RECUSADO, 415)
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
                        salvo = await registrar_experiencia(banco, dados_experiencia(valores), chave, instante,
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

"""Fronteira HTTP: origem, limites, formulários e respostas. Regras ficam nos serviços."""

from datetime import datetime, timezone
import re
import time
from urllib.parse import parse_qs, quote, urlsplit
from uuid import uuid4

import js
from pyodide.ffi import to_js
from workers import Response, WorkerEntrypoint, fetch

from acesso import DURACAO_SESSAO, MIN_SEGREDO, criar_sessao, destino_seguro, ler_registro, sessao_valida
from armazenamento import ArmazenamentoD1, ArmazenamentoDrive, ArmazenamentoR2, ErroDrive
from dominio import (CATEGORIA_PADRAO, MAX_BUSCA, MAX_FOTO_BYTES, campos_da_categoria, categoria_raiz, categoria_valida,
                     horario_local, preco_em_centavos)
from paginas import (pagina_entrar, pagina_indisponivel, pagina_inicial, formulario, confirmacao, pagina_item, formulario_item,
                     formulario_experiencia, confirmar_exclusao, texto_vai_junto, valores_item, valores_experiencia)
from servicos import (entrar, verificar_base, buscar, criar_item, registrar_experiencia, anexar_foto,
                      editar_item, editar_experiencia, excluir_experiencia, excluir_foto, excluir_item)


ESTATICOS = ("/estilo.css", "/fotos.js", "/htmx.min.js", "/seta.svg")
COOKIE_SESSAO = "sessao"
# Token de acesso do Drive reaproveitado entre requisições do mesmo isolate.
CACHE_DRIVE = {}
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


def redirecionar(url, cookie=None):
    extras = {"Set-Cookie": cookie} if cookie else {}
    return Response("", status=303, headers={**CABECALHOS, "Location": url, **extras})


async def pbkdf2_webcrypto(senha, sal, iteracoes):
    """hashlib.pbkdf2_hmac não existe no runtime; o PBKDF2 do WebCrypto dá o mesmo resultado."""
    sutil = js.crypto.subtle
    chave = await sutil.importKey("raw", to_js(senha), "PBKDF2", False, to_js(["deriveBits"]))
    algoritmo = to_js({"name": "PBKDF2", "hash": "SHA-256", "salt": to_js(sal), "iterations": iteracoes},
                      dict_converter=js.Object.fromEntries)
    return bytes(js.Uint8Array.new(await sutil.deriveBits(algoritmo, chave, 256)).to_py())


def ler_cookie(request, nome):
    for parte in request.headers.get("Cookie", "").split(";"):
        chave, _, valor = parte.strip().partition("=")
        if chave == nome:
            return valor
    return None


def cookie_sessao(request, valor, duracao):
    # Secure só fora do http local de desenvolvimento e testes.
    seguro = "; Secure" if urlsplit(request.url).scheme == "https" else ""
    return f"{COOKIE_SESSAO}={valor}; Path=/; HttpOnly; SameSite=Lax; Max-Age={duracao}{seguro}"


async def requisitar(metodo, url, cabecalhos, corpo=None):
    """HTTP de saída para o adaptador do Drive: devolve (status, bytes)."""
    opcoes = {"method": metodo, "headers": cabecalhos}
    if corpo is not None:
        opcoes["body"] = to_js(corpo)
    resposta = await fetch(url, **opcoes)
    return resposta.status, await resposta.bytes()


def armazenamento_fotos(env):
    """R2 simulado no computador e nos testes; Drive na publicação, que não tem o binding FOTOS."""
    if getattr(env, "FOTOS", None) is not None:
        return ArmazenamentoR2(env.FOTOS)
    nomes = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "GOOGLE_PASTA_ID")
    valores = [getattr(env, nome, None) for nome in nomes]
    if not all(valores):
        raise RuntimeError("Armazenamento de fotos não configurado.")
    credenciais = dict(zip(("client_id", "client_secret", "refresh_token"), valores[:3]))
    return ArmazenamentoDrive(credenciais, valores[3], requisitar, time.time, CACHE_DRIVE)


def configuracao_login(env):
    """Sem senha ou segredo válidos o app fica fechado, nunca aberto."""
    registro, segredo = getattr(env, "SENHA_HASH", None), getattr(env, "SEGREDO_SESSAO", None)
    if not registro or not segredo or len(segredo) < MIN_SEGREDO:
        return None
    try:
        ler_registro(registro)
    except ValueError:
        return None
    return registro, segredo


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
    categoria = valores.get("categoria", CATEGORIA_PADRAO)
    # Cada categoria tem seus próprios campos no formulário ("lugar-bairro", "restaurante-bairro").
    prefixo = categoria_raiz(categoria)
    return {"nome": valores.get("nome", ""), "categoria": categoria,
            "descricao": valores.get("descricao", ""),
            "detalhes": {campo: valores.get(f"{prefixo}-{campo}", "") for campo in campos_da_categoria(categoria)}}


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
    campos = parse_qs(conteudo, keep_blank_values=True, max_num_fields=80)
    if any(len(valores) != 1 for valores in campos.values()):
        raise ValueError("O formulário contém campos repetidos.")
    return {campo: valores[0] for campo, valores in campos.items()}


FORMATO_RECUSADO = {"erro": "Formato de formulário não suportado."}



class Default(WorkerEntrypoint):
    async def pagina_busca(self, banco, consulta):
        criterios = {campo: consulta.get(parametro, [""])[0] for campo, parametro in
                     (("texto", "q"), ("categoria", "categoria"), ("nota_min", "nota_min"), ("nota_max", "nota_max"))}
        try:
            pagina = identificador(consulta.get("pagina", ["1"])[0])
            return html(pagina_inicial(await buscar(banco, criterios, pagina), pagina))
        except ValueError as erro:
            # Mantém o texto digitado no campo; filtros inválidos voltam ao padrão.
            eco = {"busca": {"texto": criterios["texto"][:MAX_BUSCA], "categoria": "",
                             "nota_min": None, "nota_max": None}, "itens": [], "tem_mais": False}
            return html(pagina_inicial(eco, erro=str(erro)), 422)

    async def recurso(self, request, banco, instante, tipo, texto_id, acao):
        """Páginas, edição e exclusão de itens, experiências e fotos. None significa rota inexistente."""
        registro_id = identificador(texto_id)
        arquivos = armazenamento_fotos(self.env)
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
            if acao == "excluir" and valores is None:
                experiencias = len(await banco.listar_experiencias(registro_id))
                fotos = len(await banco.listar_fotos_do_item(registro_id))
                return html(confirmar_exclusao(
                    "Excluir este item?", f"{item['nome']}. {texto_vai_junto(experiencias, fotos)}",
                    f"/itens/{registro_id}/excluir", f"/itens/{registro_id}"))
            if acao == "excluir":
                resultado = await excluir_item(banco, arquivos, registro_id)
                if resultado["orfaos"]:
                    print("Fotos não removidas do armazenamento:", resultado["orfaos"])
                return redirecionar("/")
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
                guardada = parse_qs(urlsplit(request.url).query).get("guardada") == ["1"]
                return html(confirmacao(experiencia, await banco.listar_fotos(registro_id),
                                        await banco.listar_tags(registro_id), guardada))
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
                print("Fotos não removidas do armazenamento:", resultado["orfaos"])
            return redirecionar(f"/itens/{resultado['item_id']}")
        foto = await banco.obter_foto(registro_id)
        if not foto:
            raise LookupError("Essa foto não foi encontrada.")
        if acao is None:
            conteudo = await arquivos.obter(foto["arquivo"])
            if conteudo is None:
                raise LookupError("Essa foto não foi encontrada.")
            # A foto de um id nunca muda; o navegador guarda por um dia e poupa o Drive.
            return Response(conteudo, headers={**CABECALHOS, "Content-Type": "image/jpeg",
                                               "Cache-Control": "private, max-age=86400"})
        if acao != "excluir":
            return None
        if valores is None:
            previa = f'<img class="previa-exclusao" src="/fotos/{registro_id}" alt="Foto que será removida">'
            return html(confirmar_exclusao("Remover esta foto?", "A experiência continua; só a foto sai.",
                f"/fotos/{registro_id}/excluir", f"/experiencias/{foto['experiencia_id']}", previa))
        resultado = await excluir_foto(banco, arquivos, registro_id)
        if resultado["orfaos"]:
            print("Foto não removida do armazenamento:", resultado["orfaos"])
        return redirecionar(f"/experiencias/{resultado['experiencia_id']}")

    async def acesso(self, request, banco, instante, configuracao):
        """Login e saída. None quando a rota não é de acesso."""
        caminho = urlsplit(request.url).path
        if caminho == "/entrar" and request.method == "GET":
            volta = destino_seguro(parse_qs(urlsplit(request.url).query).get("volta", ["/"])[0])
            return html(pagina_entrar(volta))
        if caminho == "/entrar":
            valores = await ler_formulario(request)
            if valores is None:
                return resposta_json(FORMATO_RECUSADO, 415)
            volta = destino_seguro(valores.get("volta", "/"))
            registro, segredo = configuracao
            try:
                await entrar(banco, valores.get("senha", ""), registro, pbkdf2_webcrypto, instante)
            except PermissionError as erro:
                return html(pagina_entrar(volta, str(erro)), 401)
            duracao = int(DURACAO_SESSAO.total_seconds())
            return redirecionar(volta, cookie_sessao(request, criar_sessao(segredo, instante), duracao))
        if caminho == "/sair" and request.method == "POST":
            return redirecionar("/entrar", cookie_sessao(request, "", 0))
        return None

    async def fetch(self, request):
        url = urlsplit(request.url)
        caminho = url.path
        banco = ArmazenamentoD1(self.env.DB)
        instante = datetime.now(timezone.utc)
        if request.method not in ("GET", "POST"):
            return Response("Método não permitido.", status=405, headers={**CABECALHOS, "Allow": "GET, POST"})
        if request.method == "POST" and not origem_permitida(request):
            return resposta_json({"erro": "Envio recusado: abra o formulário neste site."}, 403)
        if request.method == "GET" and caminho in ESTATICOS:
            return await self.env.ASSETS.fetch(request)
        configuracao = configuracao_login(self.env)
        logado = configuracao is not None and sessao_valida(ler_cookie(request, COOKIE_SESSAO), configuracao[1], instante)
        try:
            if caminho == "/saude" and request.method == "GET":
                # Sem sessão, só confirma que o banco responde; contagens são dados do caderno.
                base = await verificar_base(banco, instante)
                return resposta_json(base if logado else {"estado": base["estado"]})
            if configuracao is None:
                return html(pagina_indisponivel("O login ainda não foi configurado. Veja o README."), 503)
            if resposta := await self.acesso(request, banco, instante, configuracao):
                return resposta
            if not logado:
                if request.method == "GET":
                    volta = caminho + (f"?{url.query}" if url.query else "")
                    return redirecionar(f"/entrar?volta={quote(volta, safe='')}")
                return resposta_json({"erro": "Sua sessão acabou. Entre de novo e repita o envio."}, 401)
            if encontrado := RECURSO.fullmatch(caminho):
                resposta = await self.recurso(request, banco, instante, *encontrado.groups())
                if resposta is not None:
                    return resposta
            elif request.method == "GET":
                consulta = parse_qs(url.query)
                if caminho == "/":
                    return await self.pagina_busca(banco, consulta)
                if caminho == "/registrar":
                    item = None
                    if consulta.get("item_id"):
                        item = await banco.obter_item(identificador(consulta["item_id"][0]))
                        if not item:
                            raise LookupError("Esse item não foi encontrado.")
                    # Vindo da aba de uma categoria, o formulário já abre nela; valor estranho é ignorado.
                    categoria = consulta.get("categoria", [""])[0]
                    valores = {"categoria": categoria} if categoria_valida(categoria) else None
                    return html(formulario(horario_local(instante)[:10], uuid4().hex, item, valores))
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
                        destino = {"url": f"/experiencias/{salvo['id']}?guardada=1", "experiencia_id": salvo["id"], "item_id": salvo["item_id"]}
                    return resposta_json(destino) if quer_json else redirecionar(destino["url"])
                except ValueError as erro:
                    if quer_json:
                        return resposta_json({"erro": str(erro)}, 422)
                    item = await banco.obter_item(item_id) if item_id else None
                    return html(formulario(horario_local(instante)[:10], valores.get("chave", ""), item, valores, str(erro)), 422)
            elif caminho.startswith("/uploads/"):
                experiencia_id = identificador(caminho.removeprefix("/uploads/"))
                conteudo = await ler_corpo(request, MAX_FOTO_BYTES)
                foto = await anexar_foto(banco, armazenamento_fotos(self.env), experiencia_id,
                    request.headers.get("X-Chave-Foto", ""), conteudo, request.headers.get("Content-Type", ""))
                return resposta_json({"id": foto["id"], "url": f"/fotos/{foto['id']}"})
        except LookupError as erro:
            return resposta_json({"erro": str(erro)}, 404)
        except ValueError as erro:
            return resposta_json({"erro": str(erro)}, 400)
        except Exception as erro:
            # Mensagens do binding podem conter SQL/dados pessoais: registrar só o tipo.
            # Exceção: ErroDrive traz só a etapa e o status HTTP, úteis para diagnosticar a publicação.
            print("Falha na operação:", type(erro).__name__, erro if isinstance(erro, ErroDrive) else "")
            return resposta_json({"erro": "Não foi possível concluir. Tente novamente; o mesmo envio não duplica o registro."}, 503)
        return Response("Essa lembrança não está aqui.", status=404, headers=CABECALHOS)

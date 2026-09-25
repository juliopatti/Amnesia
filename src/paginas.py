"""Páginas e formulários HTML; nenhum valor do usuário é inserido sem escape."""

from html import escape
import json
import re
from urllib.parse import urlencode

from dominio import VOLTARIA, centavos_em_texto, contato_telefone, resumo_notas

BUSCA_VAZIA = {"texto": "", "categoria": "", "nota_min": None, "nota_max": None}
# 422 traz a página com a mensagem de erro da busca; o htmx precisa trocá-la mesmo assim.
HTMX_CONFIG = ('{"allowEval":false,"includeIndicatorStyles":false,"responseHandling":['
               '{"code":"204","swap":false},{"code":"[23]..","swap":true},'
               '{"code":"422","swap":true},{"code":"[45]..","swap":false,"error":true}]}')


def estrutura(conteudo, titulo="Seu caderno", filtros=""):
    return f"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="htmx-config" content='{HTMX_CONFIG}'>
<title>{escape(titulo)} · amnesia</title>
<link rel="stylesheet" href="/estilo.css">
<script src="/htmx.min.js" defer></script><script src="/fotos.js" defer></script>
</head><body>
<a class="pular" href="#conteudo">Pular para o conteúdo</a>
<header><div class="topo"><a class="logo" href="/">amnesia<span aria-hidden="true">.</span></a>
<span class="selo">só para você</span></div>{filtros or formulario_busca()}</header>
<main id="conteudo">{conteudo}</main>
<footer>Uma memória externa. Sem plateia.</footer>
</body></html>"""


def nota_texto(nota):
    return f"{nota:g}".replace(".", ",")


def formulario_busca(busca=None, categorias=()):
    """Nas outras páginas, só o campo; na inicial, filtros e atualização via htmx."""
    completo = busca is not None
    busca = busca or BUSCA_VAZIA
    campo_busca = f"""<label class="sr-only" for="q">Buscar nas lembranças</label>
        <div class="campo-busca"><input id="q" name="q" type="search" value="{escape(busca['texto'])}"
        maxlength="200" autocomplete="off" enterkeyhint="search"
        placeholder="Coxinha, bairro, aquele café…"><button class="botao principal" type="submit">Buscar</button></div>"""
    if not completo:
        return f'<form class="busca" action="/" method="get" role="search">{campo_busca}</form>'
    chips = ""
    for slug, nome in [("", "Tudo")] + [(c["slug"], c["nome"]) for c in categorias]:
        marcado = "checked" if slug == busca["categoria"] else ""
        chips += (f'<input class="radio-visual" type="radio" name="categoria" id="categoria-{escape(slug) or "todas"}" '
                  f'value="{escape(slug)}" {marcado}><label class="filtro" for="categoria-{escape(slug) or "todas"}">{escape(nome)}</label>')
    faixa = ""
    for nome, rotulo in (("nota_min", "Média de"), ("nota_max", "até")):
        opcoes = '<option value="">qualquer</option>'
        for meia in range(11):
            valor = meia / 2
            opcoes += f'<option value="{valor:g}" {"selected" if busca[nome] == valor else ""}>{nota_texto(valor)}</option>'
        faixa += f'<label for="{nome}">{rotulo}</label><select id="{nome}" name="{nome}">{opcoes}</select>'
    return f"""<form id="busca" class="busca" action="/" method="get" role="search"
        hx-get="/" hx-trigger="submit, input changed delay:300ms from:#q, change from:#filtros-busca"
        hx-target="#conteudo" hx-select="#conteudo" hx-swap="outerHTML" hx-push-url="true" hx-sync="this:replace">
        {campo_busca}<div id="filtros-busca">
        <fieldset class="filtros"><legend class="sr-only">Categoria</legend>{chips}</fieldset>
        <div class="faixa" role="group" aria-label="Faixa de nota média">{faixa}</div></div></form>"""


def url_busca(busca, pagina=1):
    parametros = {"q": busca["texto"], "categoria": busca["categoria"],
                  "nota_min": "" if busca["nota_min"] is None else f"{busca['nota_min']:g}",
                  "nota_max": "" if busca["nota_max"] is None else f"{busca['nota_max']:g}",
                  "pagina": "" if pagina == 1 else pagina}
    consulta = urlencode({chave: valor for chave, valor in parametros.items() if valor != ""})
    return "/?" + consulta if consulta else "/"


def destacar(trecho):
    """Escapa o trecho da FTS e só então converte os marcadores pareados em <mark>."""
    seguro = re.sub("\x02([^\x02\x03]*)\x03", r"<mark>\1</mark>", escape(trecho))
    return seguro.replace("\x02", "").replace("\x03", "")


def cartao(item):
    trecho = item.get("trecho") or ""
    # Se o trecho é o próprio nome, a descrição informa mais.
    if trecho and trecho.replace("\x02", "").replace("\x03", "") != item["nome"]:
        resumo = f'<p class="trecho">{destacar(trecho)}</p>'
    else:
        resumo = f'<p class="descricao">{escape(item["descricao"][:180])}</p>'
    total = item.get("experiencias", 0)
    if not total:
        meta = "Nenhuma experiência ainda"
    else:
        media = "Sem nota" if item.get("media") is None else f"Média {nota_texto(round(item['media'], 2))}"
        meta = f"{media} · {total} experiência{'s' if total > 1 else ''}"
    return f"""<li class="item">
        <div><span class="categoria">{'Lugar' if item['categoria'] == 'lugar' else 'Produto'}</span>
        <h2><a class="nome-item" href="/itens/{item['id']}">{escape(item['nome'])}</a></h2>{resumo}<p class="meta">{meta}</p></div>
        <a class="botao secundario" href="/registrar?item_id={item['id']}"
           aria-label="Registrar experiência em {escape(item['nome'])}">Registrar <span aria-hidden="true">↗</span></a>
        </li>"""


def pagina_inicial(categorias, resultado=None, pagina=1, erro=""):
    resultado = resultado or {"busca": dict(BUSCA_VAZIA), "itens": [], "tem_mais": False}
    busca, itens = resultado["busca"], resultado["itens"]
    filtrando = bool(erro) or any((busca["texto"], busca["categoria"],
                                   busca["nota_min"] is not None, busca["nota_max"] is not None))
    cartoes = "".join(cartao(item) for item in itens)
    limpar = '<a class="botao secundario" href="/">Limpar busca</a>'
    if erro:
        cartoes = ""
    elif not cartoes and busca["texto"] and not busca.get("expressao"):
        cartoes = f'<li class="vazio"><span aria-hidden="true">?</span><h2>Só sobrou pontuação.</h2><p>Tente uma palavra. “Coxinha” costuma funcionar.</p>{limpar}</li>'
    elif not cartoes and filtrando:
        termo = f" com “{escape(busca['texto'])}”" if busca["texto"] else " com esses filtros"
        cartoes = f'<li class="vazio"><span aria-hidden="true">∅</span><h2>Nenhuma lembrança{termo}.</h2><p>Talvez tenha outro nome. Talvez tenha sido um sonho.</p>{limpar}</li>'
    elif not cartoes:
        cartoes = '<li class="vazio"><span aria-hidden="true">↳</span><h2>A memória começa aqui.</h2><p>Ou você nunca foi, ou esqueceu de anotar também.</p></li>'
    paginacao = ""
    if pagina > 1:
        paginacao += f'<a href="{escape(url_busca(busca, pagina - 1))}">← Anteriores</a>'
    if resultado["tem_mais"]:
        paginacao += f'<a href="{escape(url_busca(busca, pagina + 1))}">Próximos →</a>'
    if filtrando:
        quantidade = len(itens) + (pagina - 1) * 20
        contagem = "Nada encontrado" if not itens else f"{quantidade}{'+' if resultado['tem_mais'] else ''} {'item encontrado' if quantidade == 1 else 'itens encontrados'}"
        topo = f'<div class="resultados"><h1 class="titulo-busca">Resultados</h1><p class="muted" role="status">{contagem}</p></div>'
    else:
        topo = """<section class="abertura"><p class="sobretitulo">SEU CADERNO DE EXPERIÊNCIAS</p>
        <h1>Foi bom?<br><span>Melhor anotar.</span></h1>
        <p>Você já esteve aqui. Óbvio que não lembra.</p>
        <a class="botao principal" href="/registrar">+ Registrar experiência</a></section>
        <div class="titulo-lista"><h2>O que ficou na memória</h2></div>"""
    aviso = f'<div class="aviso erro" role="alert">{escape(erro)}</div>' if erro else ""
    return estrutura(f"""{topo}{aviso}<ul class="itens">{cartoes}</ul>
        <nav class="paginacao" aria-label="Paginação">{paginacao}</nav>""",
        "Busca" if filtrando else "Seu caderno", formulario_busca(busca, categorias))


def campo(nome, rotulo, valores, tipo="text", atributos="", ajuda=""):
    valor = escape(str(valores.get(nome, "")), quote=True)
    ajuda_html = f'<small id="ajuda-{nome}">{ajuda}</small>' if ajuda else ""
    descrito = f'aria-describedby="ajuda-{nome}"' if ajuda else ""
    return f'<label for="{nome}">{rotulo}</label><input id="{nome}" name="{nome}" type="{tipo}" value="{valor}" {atributos} {descrito}>{ajuda_html}'


def texto(nome, rotulo, valores, placeholder="", limite=10000):
    return f'<label for="{nome}">{rotulo}</label><textarea id="{nome}" name="{nome}" maxlength="{limite}" rows="3" placeholder="{placeholder}">{escape(valores.get(nome, ""))}</textarea>'


def estrelas(nota=""):
    selecionada = str(nota).replace(",", ".")
    if selecionada.endswith(".0"):
        selecionada = selecionada[:-2]
    def opcao(valor, rotulo, classe=""):
        selecionado = "checked" if selecionada == valor else ""
        identificador = "nota-" + (valor.replace(".", "-") or "vazia")
        return f'<input class="radio-visual" type="radio" name="nota" id="{identificador}" value="{valor}" {selecionado}><label class="{classe}" for="{identificador}">{rotulo}</label>'
    botoes = opcao("", "Sem nota", "opcao-nota") + opcao("0", "0 estrelas", "opcao-nota")
    grupo = ""
    for inteira in range(1, 6):
        grupo += f'<span class="estrela" data-estrela="{inteira}"><span class="desenho" aria-hidden="true">★</span>'
        for valor, classe in ((str(inteira - 0.5), "metade"), (str(inteira), "inteira")):
            grupo += opcao(valor, f'<span class="sr-only">{valor.replace(".", ",")} estrelas</span>', classe)
        grupo += '</span>'
    return f'<fieldset class="avaliacao"><legend>Que nota merece?</legend><div class="opcoes-nota">{botoes}</div><div class="estrelas">{grupo}</div><output class="nota-atual" aria-live="polite" hidden>{escape(selecionada or "Sem nota")}</output><small>Toque na metade esquerda para meia estrela; na direita para uma inteira.</small></fieldset>'


def seletor_fotos():
    return """<div class="campo-fotos"><label for="fotos">Fotos <span class="opcional">opcional</span></label>
    <input id="fotos" type="file" accept="image/*" multiple aria-describedby="ajuda-fotos">
    <small id="ajuda-fotos">Até 3 fotos. A gente diminui antes de enviar.</small>
    <ul id="previas" class="previas"></ul>
    <noscript><p>O registro funciona sem JavaScript. Para reduzir e enviar fotos, ative o JavaScript.</p></noscript></div>"""


def nome_categoria(categoria):
    return "Lugar" if categoria == "lugar" else "Produto"


def estrelas_leitura(nota):
    """Estrelas só para leitura, na meia estrela mais próxima; o rótulo traz o número exato.

    A CSP proíbe style inline, por isso o preenchimento usa uma classe por meia estrela.
    """
    if nota is None:
        return ""
    meias = int(nota * 2 + 0.5)
    rotulo = f"{nota_texto(round(nota, 2))} de 5"
    return (f'<span class="estrelas-leitura" role="img" aria-label="{rotulo}">'
            f'<span class="cheias meias-{meias}">★★★★★</span>★★★★★</span>')


def resumo_media(notas):
    resumo = resumo_notas(notas)
    if not resumo["experiencias"]:
        return ""
    total = resumo["experiencias"]
    plural = "experiência" if total == 1 else "experiências"
    if resumo["media"] is None:
        return f'<p class="media-item"><span class="numero-media">Sem nota</span> <span class="muted">{total} {plural}</span></p>'
    avaliadas = "" if resumo["avaliadas"] == total else f', {resumo["avaliadas"]} com nota'
    return (f'<p class="media-item">{estrelas_leitura(resumo["media"])}'
            f'<span class="numero-media">{nota_texto(round(resumo["media"], 2))}</span>'
            f'<span class="muted">média de {total} {plural}{avaliadas}</span></p>')


def texto_voltaria(voltaria):
    return "" if voltaria is None else f'<p class="voltaria-resposta">Voltaria? <strong>{escape(VOLTARIA[voltaria])}</strong></p>'


def texto_nota(nota):
    return "Sem nota" if nota is None else f"{nota_texto(nota)} / 5"


def campos_identificacao(valores):
    html = '<div class="linha"><div><label for="categoria">O que é?</label><select id="categoria" name="categoria">'
    for slug, nome in (("lugar", "Lugar"), ("produto", "Produto")):
        html += f'<option value="{slug}" {"selected" if valores["categoria"] == slug else ""}>{nome}</option>'
    return html + '</select></div><div class="crescer">' + campo("nome", "Nome", valores, atributos='required maxlength="200" autocomplete="off" placeholder="Aquele bar da esquina…"') + '</div></div>'


def campos_item(valores):
    html = texto("descricao", "Sobre o lugar ou produto", valores, "O que vale lembrar sobre ele?")
    texto_livre = ("text", 'maxlength="1000"')
    telefone = ("tel", 'inputmode="tel" autocomplete="off" maxlength="30" placeholder="(11) 98765-4321"')
    for categoria, campos in (("lugar", (("endereco", "Endereço", texto_livre), ("bairro", "Bairro", texto_livre),
                                         ("cidade", "Cidade", texto_livre), ("telefone", "Telefone / WhatsApp", telefone))),
                              ("produto", (("marca", "Marca", texto_livre), ("onde_comprei", "Onde comprei", texto_livre),
                                           ("link", "Link", ("url", 'maxlength="1000" placeholder="https://"'))))):
        html += f'<div data-categoria="{categoria}"><p class="categoria">Detalhes do {"lugar" if categoria == "lugar" else "produto"}</p>'
        html += "".join(campo(nome, rotulo, valores, tipo, atributos) for nome, rotulo, (tipo, atributos) in campos)
        html += '</div>'
    return html


def campos_experiencia(valores):
    voltaria = '<fieldset class="voltaria"><legend>Voltaria / compraria de novo?</legend><div class="opcoes-voltaria">'
    for valor, rotulo in [("", "Sem resposta")] + [(str(nivel), texto) for nivel, texto in VOLTARIA.items()]:
        identificador = f"voltaria-{valor or 'vazia'}"
        marcado = "checked" if str(valores.get("voltaria", "")) == valor else ""
        voltaria += (f'<input class="radio-visual" type="radio" name="voltaria" id="{identificador}" value="{valor}" {marcado}>'
                     f'<label class="opcao-nota" for="{identificador}">{escape(rotulo)}</label>')
    voltaria += '</div></fieldset>'
    return (campo("data", "Quando foi?", valores, "date") + campo("pedido", "O que pedi ou provei", valores, atributos='maxlength="10000"')
            + campo("preco", "Quanto paguei (R$)", valores, atributos='inputmode="decimal" maxlength="20" placeholder="12,50"')
            + voltaria + campo("tags", "Tags", valores, atributos='maxlength="1100" placeholder="coxinha, happy hour"', ajuda="Separe por vírgulas. Até 20 tags."))


def aviso_erro(erro):
    return f'<div id="erro-form" class="aviso erro" role="alert" {"hidden" if not erro else ""}>{escape(erro)}</div>'


def formulario(hoje, chave, item=None, valores=None, erro=""):
    valores = dict(valores or {})
    valores.setdefault("data", hoje)
    valores.setdefault("categoria", "lugar")
    titulo = "Mais uma lembrança" if item else "Guardar uma experiência"
    if item:
        identificacao = f'<input type="hidden" name="item_id" value="{item["id"]}"><div class="item-escolhido"><span class="categoria">{nome_categoria(item["categoria"])}</span><h2>{escape(item["nome"])}</h2><a href="/">Escolher outro item</a></div>'
    else:
        identificacao = campos_identificacao(valores)
    extras = campos_experiencia(valores) + ("" if item else campos_item(valores))
    salvar_item = '<button class="botao texto-botao" type="submit" name="acao" value="item">Só guardar o item, sem experiência</button>' if item is None else ""
    return estrutura(f"""<a class="voltar" href="/">← Meu caderno</a><h1 class="titulo-form">{titulo}</h1>
        <p class="muted">Anote agora. Seu eu do futuro agradece.</p>
        {aviso_erro(erro)}
        <form id="cadastro" action="/registros" method="post">
        <input type="hidden" name="chave" value="{escape(chave)}">
        {identificacao}{estrelas(valores.get('nota', ''))}
        {texto('texto', 'Como foi?', valores, 'A coxinha prometeu tudo. Entregou arrependimento.')}
        <details {'open' if erro else ''}><summary>Mais detalhes <span>data, preço, tags e descrição</span></summary>{extras}</details>
        {seletor_fotos()}<div class="acoes"><button class="botao principal" type="submit" name="acao" value="experiencia">Guardar experiência</button>{salvar_item}</div>
        </form><section id="resultado-upload" class="aviso" aria-live="polite" hidden></section>""", titulo)


def valores_item(item):
    """Converte o registro do banco nos valores exibidos pelo formulário de edição."""
    return {"nome": item["nome"], "categoria": item["categoria"], "descricao": item["descricao"],
            **json.loads(item["detalhes"] or "{}")}


def valores_experiencia(experiencia, tags):
    nota = experiencia["nota"]
    return {"data": experiencia["data"], "nota": "" if nota is None else f"{nota:g}",
            "texto": experiencia["texto"], "pedido": experiencia["pedido"],
            "preco": centavos_em_texto(experiencia["preco_centavos"]),
            "voltaria": "" if experiencia["voltaria"] is None else str(experiencia["voltaria"]),
            "tags": ", ".join(tags)}


def formulario_item(item, valores, erro=""):
    return estrutura(f"""<a class="voltar" href="/itens/{item['id']}">← Voltar ao item</a>
        <h1 class="titulo-form">Editar item</h1><p class="muted">Errar o nome acontece. Esquecer que errou, também.</p>
        {aviso_erro(erro)}
        <form id="editar-item" action="/itens/{item['id']}/editar" method="post">
        {campos_identificacao(valores)}{campos_item(valores)}
        <div class="acoes"><button class="botao principal" type="submit">Guardar alterações</button>
        <a href="/itens/{item['id']}">Cancelar</a></div></form>""", "Editar item")


def formulario_experiencia(experiencia, valores, erro=""):
    return estrutura(f"""<a class="voltar" href="/experiencias/{experiencia['id']}">← Voltar à experiência</a>
        <h1 class="titulo-form">Editar experiência</h1>
        <div class="item-escolhido"><span class="categoria">{nome_categoria(experiencia['categoria'])}</span><h2>{escape(experiencia['nome'])}</h2></div>
        {aviso_erro(erro)}
        <form id="editar-experiencia" action="/experiencias/{experiencia['id']}/editar" method="post">
        {estrelas(valores.get('nota', ''))}
        {texto('texto', 'Como foi?', valores)}{campos_experiencia(valores)}
        <div class="acoes"><button class="botao principal" type="submit">Guardar alterações</button>
        <a href="/experiencias/{experiencia['id']}">Cancelar</a></div></form>""", "Editar experiência")


def confirmar_exclusao(titulo, explicacao, acao, voltar, extra=""):
    return estrutura(f"""<a class="voltar" href="{voltar}">← Voltar</a>
        <p class="sobretitulo">SEM VOLTA</p><h1 class="titulo-form">{escape(titulo)}</h1>
        <p class="muted">{escape(explicacao)}</p>{extra}
        <form action="{acao}" method="post"><div class="acoes">
        <button class="botao perigo" type="submit">Excluir de vez</button>
        <a href="{voltar}">Melhor não</a></div></form>""", titulo)


def confirmacao(experiencia, fotos):
    imagens = "".join(
        f'<li><img src="/fotos/{foto["id"]}" alt="Foto {indice+1} desta experiência" loading="lazy">'
        f'<a class="remover" href="/fotos/{foto["id"]}/excluir">Remover foto {indice+1}</a></li>'
        for indice, foto in enumerate(fotos))
    return estrutura(f"""<a class="voltar" href="/itens/{experiencia['item_id']}">← {escape(experiencia['nome'])}</a>
        <p class="sobretitulo">LEMBRANÇA GUARDADA</p><h1 class="titulo-form">Pode esquecer.<br>A gente anotou.</h1>
        <article class="resumo"><span class="categoria">{escape(experiencia['data'])} · {escape(texto_nota(experiencia['nota']))}</span>
        <h2>{escape(experiencia['nome'])}</h2><p class="relato">{escape(experiencia['texto'])}</p>
        <p>{escape(experiencia['pedido'])}</p>{texto_voltaria(experiencia['voltaria'])}
        <p class="editar"><a href="/experiencias/{experiencia['id']}/editar">Editar experiência</a>
        <a href="/experiencias/{experiencia['id']}/excluir">Excluir</a></p></article><ul class="galeria">{imagens}</ul>
        <form id="anexar-fotos" data-experiencia="{experiencia['id']}" data-total="{len(fotos)}">
        {seletor_fotos()}<button class="botao secundario" type="submit">Anexar fotos</button></form>
        <section id="resultado-upload" class="aviso" aria-live="polite" hidden></section>
        <div class="acoes"><a class="botao principal" href="/registrar?item_id={experiencia['item_id']}">Outra experiência aqui</a>
        <a href="/">Voltar ao caderno</a></div>""", "Experiência guardada")


def contatos_item(detalhes):
    """Endereço em texto; telefone e link viram ações. Link e telefone já foram validados."""
    linhas = []
    local = " · ".join(detalhes[c] for c in ("endereco", "bairro", "cidade", "marca", "onde_comprei") if detalhes.get(c))
    if local:
        linhas.append(f'<p class="muted">{escape(local)}</p>')
    acoes = ""
    if detalhes.get("telefone"):
        contato = contato_telefone(detalhes["telefone"])
        acoes += f'<a class="botao secundario" href="{escape(contato["ligar"])}">Ligar · {escape(detalhes["telefone"])}</a>'
        if contato["whatsapp"]:
            acoes += f'<a class="botao secundario" href="{escape(contato["whatsapp"])}" rel="noopener noreferrer">WhatsApp</a>'
    if detalhes.get("link"):
        acoes += f'<a class="botao secundario" href="{escape(detalhes["link"])}" rel="noopener noreferrer">Abrir link</a>'
    if acoes:
        linhas.append(f'<div class="contatos">{acoes}</div>')
    return "".join(linhas)


def pagina_item(item, experiencias):
    """Lista simples das experiências para chegar à edição; a linha do tempo completa é o incremento 4."""
    detalhes = json.loads(item["detalhes"] or "{}")
    lista = "".join(
        f'<li><a href="/experiencias/{e["id"]}"><span class="categoria">{escape(e["data"])} · {escape(texto_nota(e["nota"]))}</span>'
        f'<span class="relato-curto">{escape(e["texto"][:140]) or "Sem relato."}</span></a></li>'
        for e in experiencias)
    if not lista:
        lista = '<li class="vazio"><p>Nenhuma experiência ainda. Suspeito.</p></li>'
    return estrutura(f"""<a class="voltar" href="/">← Meu caderno</a>
        <p class="sobretitulo">{nome_categoria(item['categoria']).upper()}</p><h1 class="titulo-form">{escape(item['nome'])}</h1>
        {resumo_media([e['nota'] for e in experiencias])}
        {f'<p class="relato">{escape(item["descricao"])}</p>' if item['descricao'] else ''}
        {contatos_item(detalhes)}
        <p class="editar"><a href="/itens/{item['id']}/editar">Editar item</a></p>
        <div class="acoes"><a class="botao principal" href="/registrar?item_id={item['id']}">Registrar uma experiência</a></div>
        <h2>Experiências</h2><ul class="experiencias">{lista}</ul>""", item["nome"])

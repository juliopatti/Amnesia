"""Páginas e formulários HTML; nenhum valor do usuário é inserido sem escape."""

from html import escape


def estrutura(conteudo, titulo="Seu caderno"):
    return f"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="htmx-config" content='{{"allowEval":false,"includeIndicatorStyles":false}}'>
<title>{escape(titulo)} · amnesia</title>
<link rel="stylesheet" href="/estilo.css">
<script src="/htmx.min.js" defer></script><script src="/fotos.js" defer></script>
</head><body>
<a class="pular" href="#conteudo">Pular para o conteúdo</a>
<header><a class="logo" href="/">amnesia<span aria-hidden="true">.</span></a>
<span class="selo">só para você</span></header>
<main id="conteudo">{conteudo}</main>
<footer>Uma memória externa. Sem plateia.</footer>
</body></html>"""


def pagina_inicial(categorias, itens=(), categoria="", pagina=1):
    filtros = [("", "Tudo")] + [(c["slug"], c["nome"]) for c in categorias]
    navegacao = "".join(
        f'<a class="filtro {"ativo" if slug == categoria else ""}" href="/?categoria={escape(slug)}" '
        f'hx-get="/?categoria={escape(slug)}" hx-target="#conteudo" hx-select="#conteudo" '
        f'hx-swap="outerHTML" hx-push-url="true" '
        f'{"aria-current=page" if slug == categoria else ""}>{escape(nome)}</a>'
        for slug, nome in filtros)
    cartoes = "".join(f"""<li class="item">
        <div><span class="categoria">{'Lugar' if i['categoria'] == 'lugar' else 'Produto'}</span>
        <h2>{escape(i['nome'])}</h2>
        <p class="descricao">{escape(i['descricao'][:180])}</p></div>
        <a class="botao secundario" href="/registrar?item_id={i['id']}"
           aria-label="Registrar experiência em {escape(i['nome'])}">Registrar <span aria-hidden="true">↗</span></a>
        </li>""" for i in itens[:20])
    if not cartoes:
        cartoes = '<li class="vazio"><span aria-hidden="true">↳</span><h2>A memória começa aqui.</h2><p>Ou você nunca foi, ou esqueceu de anotar também.</p></li>'
    paginacao = ""
    if pagina > 1:
        paginacao += f'<a href="/?categoria={escape(categoria)}&amp;pagina={pagina-1}">← Anteriores</a>'
    if len(itens) > 20:
        paginacao += f'<a href="/?categoria={escape(categoria)}&amp;pagina={pagina+1}">Próximos →</a>'
    return estrutura(f"""<section class="abertura"><p class="sobretitulo">SEU CADERNO DE EXPERIÊNCIAS</p>
        <h1>Foi bom?<br><span>Melhor anotar.</span></h1>
        <p>Você já esteve aqui. Óbvio que não lembra.</p>
        <a class="botao principal" href="/registrar">+ Registrar experiência</a></section>
        <div class="titulo-lista"><h2>O que ficou na memória</h2></div>
        <nav class="filtros" aria-label="Categorias">{navegacao}</nav>
        <ul class="itens">{cartoes}</ul><nav class="paginacao" aria-label="Paginação">{paginacao}</nav>""")


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


def formulario(hoje, chave, item=None, valores=None, erro=""):
    valores = dict(valores or {})
    valores.setdefault("data", hoje)
    valores.setdefault("categoria", "lugar")
    titulo = "Mais uma lembrança" if item else "Guardar uma experiência"
    identificacao = f'<input type="hidden" name="item_id" value="{item["id"]}"><div class="item-escolhido"><span class="categoria">{"Lugar" if item["categoria"] == "lugar" else "Produto"}</span><h2>{escape(item["nome"])}</h2><a href="/">Escolher outro item</a></div>' if item else ""
    if item is None:
        identificacao += '<div class="linha"><div><label for="categoria">O que é?</label><select id="categoria" name="categoria">'
        for slug, nome in (("lugar", "Lugar"), ("produto", "Produto")):
            identificacao += f'<option value="{slug}" {"selected" if valores["categoria"] == slug else ""}>{nome}</option>'
        identificacao += '</select></div><div class="crescer">' + campo("nome", "Nome", valores, atributos='required maxlength="200" autocomplete="off" placeholder="Aquele bar da esquina…"') + '</div></div>'
    extra_item = ""
    if item is None:
        extra_item = texto("descricao", "Sobre o lugar ou produto", valores, "O que vale lembrar sobre ele?")
        for categoria, campos in (("lugar", (("endereco", "Endereço"), ("bairro", "Bairro"), ("cidade", "Cidade"))),
                                  ("produto", (("marca", "Marca"), ("onde_comprei", "Onde comprei"), ("link", "Link")))):
            extra_item += f'<div data-categoria="{categoria}"><p class="categoria">Detalhes do {"lugar" if categoria == "lugar" else "produto"}</p>'
            extra_item += "".join(campo(nome, rotulo, valores, atributos='maxlength="1000"') for nome, rotulo in campos)
            extra_item += '</div>'
    repetiria = '<label for="repetiria">Voltaria / compraria de novo?</label><select id="repetiria" name="repetiria">'
    for valor, rotulo in (("", "Ainda não sei"), ("sim", "Sim"), ("nao", "Não")):
        repetiria += f'<option value="{valor}" {"selected" if valores.get("repetiria", "") == valor else ""}>{rotulo}</option>'
    repetiria += '</select>'
    extras = (campo("data", "Quando foi?", valores, "date") + campo("pedido", "O que pedi ou provei", valores, atributos='maxlength="10000"')
              + campo("preco", "Quanto paguei (R$)", valores, atributos='inputmode="decimal" maxlength="20" placeholder="12,50"')
              + repetiria + campo("tags", "Tags", valores, atributos='maxlength="1100" placeholder="coxinha, happy hour"', ajuda="Separe por vírgulas. Até 20 tags.") + extra_item)
    salvar_item = '<button class="botao texto-botao" type="submit" name="acao" value="item">Só guardar o item, sem experiência</button>' if item is None else ""
    return estrutura(f"""<a class="voltar" href="/">← Meu caderno</a><h1 class="titulo-form">{titulo}</h1>
        <p class="muted">Anote agora. Seu eu do futuro agradece.</p>
        <div id="erro-form" class="aviso erro" role="alert" {'hidden' if not erro else ''}>{escape(erro)}</div>
        <form id="cadastro" action="/registros" method="post">
        <input type="hidden" name="chave" value="{escape(chave)}">
        {identificacao}{estrelas(valores.get('nota', ''))}
        {texto('texto', 'Como foi?', valores, 'A coxinha prometeu tudo. Entregou arrependimento.')}
        <details {'open' if erro else ''}><summary>Mais detalhes <span>data, preço, tags e descrição</span></summary>{extras}</details>
        {seletor_fotos()}<div class="acoes"><button class="botao principal" type="submit" name="acao" value="experiencia">Guardar experiência</button>{salvar_item}</div>
        </form><section id="resultado-upload" class="aviso" aria-live="polite" hidden></section>""", titulo)


def confirmacao(experiencia, fotos):
    nota = "Sem nota" if experiencia["nota"] is None else f'{experiencia["nota"]:g}'.replace('.', ',') + ' / 5'
    imagens = "".join(f'<li><img src="/fotos/{foto["id"]}" alt="Foto {indice+1} desta experiência" loading="lazy"></li>' for indice, foto in enumerate(fotos))
    return estrutura(f"""<a class="voltar" href="/">← Meu caderno</a>
        <p class="sobretitulo">LEMBRANÇA GUARDADA</p><h1 class="titulo-form">Pode esquecer.<br>A gente anotou.</h1>
        <article class="resumo"><span class="categoria">{escape(experiencia['data'])} · {escape(nota)}</span>
        <h2>{escape(experiencia['nome'])}</h2><p class="relato">{escape(experiencia['texto'])}</p>
        <p>{escape(experiencia['pedido'])}</p></article><ul class="galeria">{imagens}</ul>
        <form id="anexar-fotos" data-experiencia="{experiencia['id']}" data-total="{len(fotos)}">
        {seletor_fotos()}<button class="botao secundario" type="submit">Anexar fotos</button></form>
        <section id="resultado-upload" class="aviso" aria-live="polite" hidden></section>
        <div class="acoes"><a class="botao principal" href="/registrar?item_id={experiencia['item_id']}">Outra experiência aqui</a>
        <a href="/">Voltar ao caderno</a></div>""", "Experiência guardada")


def item_guardado(item):
    return estrutura(f'<p class="sobretitulo">ITEM GUARDADO</p><h1 class="titulo-form">{escape(item["nome"])}</h1><p class="relato">{escape(item["descricao"])}</p><div class="acoes"><a class="botao principal" href="/registrar?item_id={item["id"]}">Registrar uma experiência</a><a href="/">Voltar ao caderno</a></div>', "Item guardado")

"""Regras puras: sem HTTP, banco, relógio global ou imports do Worker."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import urlsplit


FUSO_LOCAL = timezone(timedelta(hours=-3))
CAMPOS_LOCAL = (("endereco", "Endereço"), ("bairro", "Bairro"), ("cidade", "Cidade"),
                ("telefone", "Telefone / WhatsApp"))
# Fonte única das categorias raiz, na ordem de exibição. A tabela `categorias` guarda os
# mesmos slugs para integridade referencial; um teste garante que as duas listas batem.
# Subcategorias usam o slug da raiz como prefixo ("musica.rock") e herdam os campos dela.
CATEGORIAS = {
    "restaurante": {"nome": "Bares e restaurantes", "singular": "Bar ou restaurante",
                    "exemplo": "Aquele bar da esquina…",
                    "relato": "Aquele atendimento supimpa…", "campos": CAMPOS_LOCAL},
    "lugar": {"nome": "Lugares", "singular": "Lugar", "exemplo": "Aquele lugar sem pessoas…",
              "relato": "Lindo. Pena que todo mundo teve a mesma ideia.", "campos": CAMPOS_LOCAL},
    "produto": {"nome": "Produtos", "singular": "Produto", "exemplo": "Aquela obra de arte…", "relato": "Na foto parecia maior.",
                "campos": (("marca", "Marca"), ("onde_comprei", "Onde comprei"), ("link", "Link"))},
    "filme": {"nome": "Filmes", "singular": "Filme", "exemplo": "Aquele em que você dormiu no meio…",
              "relato": "Dormi no meio. Acordei no final. Não perdi nada.",
              "campos": (("direcao", "Direção"), ("ano", "Ano"), ("onde_assisti", "Onde assisti"))},
    "serie": {"nome": "Séries", "singular": "Série", "exemplo": "A que você largou na segunda temporada…",
              "relato": "Três temporadas boas e uma que fingimos que não existiu.",
              "campos": (("criacao", "Criação"), ("ano", "Ano"), ("onde_assisti", "Onde assisti"))},
    "livro": {"nome": "Livros", "singular": "Livro", "exemplo": "O que está na cabeceira há um ano…",
              "relato": "Comecei empolgado. Parei na página 43.",
              "campos": (("autoria", "Autoria"), ("editora", "Editora"), ("ano", "Ano"))},
    "musica": {"nome": "Música", "singular": "Música", "exemplo": "Perdida na playlist de 8 anos atrás…",
               "relato": "Ouvi 40 vezes seguidas. Os vizinhos também.",
               "campos": (("artista", "Artista"), ("album", "Álbum"), ("ano", "Ano"), ("link", "Link"))},
}
CATEGORIA_PADRAO = "restaurante"
MAX_FOTO_BYTES = 768 * 1024
# "Voltaria?" do mais animado ao mais contrariado; None é sem resposta.
VOLTARIA = {
    5: "Sem sombra de dúvidas",
    4: "Voltaria, ué",
    3: "Talvez",
    2: "Uai, sei não",
    1: "Não por livre espontânea vontade",
    0: "Nem a pau, Juvenal!",
}
MAX_FOTOS = 3
MAX_BUSCA = 200
MAX_TERMOS = 10
# Letras e dígitos, incluindo acentos combinantes (texto em NFD); "_" separa palavras.
TERMO = re.compile(r"(?:[^\W_]|[\u0300-\u036f])+")
DIMINUTIVOS = ("zinhos", "zinhas", "zinho", "zinha", "inhos", "inhas", "inho", "inha")
VOGAIS = "aeiou\u00e1\u00e9\u00ed\u00f3\u00fa\u00e2\u00ea\u00f4\u00e3\u00f5\u00e0"


def texto_limpo(valor, campo, limite=10000):
    if not isinstance(valor, str):
        raise ValueError(f"{campo} precisa ser texto.")
    valor = valor.strip()
    if len(valor) > limite:
        raise ValueError(f"{campo}: use até {limite} caracteres.")
    return valor


def normalizar_nota(valor):
    """Aceita 0 a 5, de meia em meia estrela; vazio significa não avaliado."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float, Decimal)):
        raise ValueError("Informe uma nota de 0 a 5, em passos de 0,5.")
    try:
        nota = Decimal(str(valor).strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError("Informe uma nota de 0 a 5, em passos de 0,5.") from None
    if not nota.is_finite() or nota not in (0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5):
        raise ValueError("Informe uma nota de 0 a 5, em passos de 0,5.")
    return float(nota)


def resumo_notas(notas):
    """Mesma regra da busca: zero é avaliação, None ("sem nota") fica fora da média."""
    avaliadas = [nota for nota in notas if nota is not None]
    return {"media": sum(avaliadas) / len(avaliadas) if avaliadas else None,
            "avaliadas": len(avaliadas), "experiencias": len(notas)}


def resumo_voltaria(respostas):
    """Respostas da mais recente para a mais antiga; "voltaria" conta os dois níveis de sim (4 e 5)."""
    respondidas = [resposta for resposta in respostas if resposta is not None]
    if not respondidas:
        return None
    return {"sim": sum(resposta >= 4 for resposta in respondidas), "respondidas": len(respondidas),
            "ultima": VOLTARIA[respondidas[0]]}


def horario_local(instante):
    """O chamador fornece o relógio; o domínio só converte para o offset fixo."""
    if not isinstance(instante, datetime) or instante.utcoffset() is None:
        raise ValueError("O horário precisa informar o fuso.")
    return instante.astimezone(FUSO_LOCAL).isoformat(timespec="seconds")


def categoria_raiz(categoria):
    """"musica.rock" → "musica". A raiz define os campos; o banco confirma que o slug existe."""
    return categoria.split(".", 1)[0]


def campos_da_categoria(categoria):
    """Nomes dos campos de detalhe; categoria desconhecida não tem nenhum."""
    definicao = CATEGORIAS.get(categoria_raiz(categoria)) if isinstance(categoria, str) else None
    return tuple(campo for campo, _ in definicao["campos"]) if definicao else ()


def categoria_valida(categoria):
    return (isinstance(categoria, str) and categoria_raiz(categoria) in CATEGORIAS
            and bool(re.fullmatch(r"[a-z]+(?:\.[a-z]+)*", categoria)))


def preparar_item(nome, categoria=CATEGORIA_PADRAO, descricao="", detalhes=None):
    nome = texto_limpo(nome, "Nome", 200)
    if not nome:
        raise ValueError("Dê um nome para conseguir lembrar depois.")
    if not categoria_valida(categoria):
        raise ValueError("Categoria desconhecida.")
    if detalhes is None:
        detalhes = {}
    if not isinstance(detalhes, dict):
        raise ValueError("Os detalhes precisam ser um objeto.")
    if any(campo not in campos_da_categoria(categoria) for campo in detalhes):
        raise ValueError("Há detalhes que não pertencem a essa categoria.")
    detalhes = {campo: texto_limpo(valor, campo, 1000) for campo, valor in detalhes.items()}
    if detalhes.get("telefone"):
        contato_telefone(detalhes["telefone"])
    if detalhes.get("ano") and not re.fullmatch(r"[0-9]{4}", detalhes["ano"]):
        raise ValueError("Ano: use quatro dígitos, como 1999.")
    if detalhes.get("link"):
        try:
            link = urlsplit(detalhes["link"])
            valido = link.scheme in ("http", "https") and bool(link.hostname)
        except ValueError:
            valido = False
        if not valido:
            raise ValueError("O link precisa começar com http:// ou https:// e ter um endereço.")
    return {
        "nome": nome,
        "categoria": categoria,
        "descricao": texto_limpo(descricao, "Descrição"),
        "detalhes": detalhes,
    }


def contato_telefone(telefone):
    """Valida o telefone como digitado e monta os destinos de ligação e WhatsApp.

    Com DDD (10 ou 11 dígitos), assume o Brasil (+55). Com "+", o número já é
    internacional. Sem DDD ou 0800, só dá para ligar: o WhatsApp exige o número completo.
    """
    if not re.fullmatch(r"\+?[0-9 ().-]+", telefone):
        raise ValueError("Telefone: use só números, espaços, parênteses, + e -.")
    digitos = re.sub(r"[^0-9]", "", telefone)
    if not 8 <= len(digitos) <= 15:
        raise ValueError("Telefone: informe de 8 a 15 dígitos.")
    if not telefone.startswith("+"):
        if digitos.startswith(("0300", "0500", "0800", "0900")):
            return {"ligar": f"tel:{digitos}", "whatsapp": None}
        digitos = digitos.lstrip("0")
        if len(digitos) not in (10, 11):
            return {"ligar": f"tel:{digitos}", "whatsapp": None}
        digitos = "55" + digitos
    return {"ligar": f"tel:+{digitos}", "whatsapp": f"https://wa.me/{digitos}"}


def preparar_experiencia(
    item_id, *, hoje, data=None, nota=None, texto="", pedido="",
    preco_centavos=None, voltaria=None, tags=(),
):
    if item_id is not None and (type(item_id) is not int or item_id <= 0):
        raise ValueError("Informe um item válido.")
    data = hoje if data is None or data == "" else data
    try:
        data_validada = date.fromisoformat(data)
    except (TypeError, ValueError):
        raise ValueError("Informe uma data válida no formato AAAA-MM-DD.") from None
    if data_validada.isoformat() != data:
        raise ValueError("Informe uma data válida no formato AAAA-MM-DD.")
    if preco_centavos is not None and (type(preco_centavos) is not int or preco_centavos < 0):
        raise ValueError("O preço precisa ser um inteiro em centavos, maior ou igual a zero.")
    if voltaria is not None and (type(voltaria) is not int or voltaria not in VOLTARIA):
        raise ValueError("Escolha uma das respostas de “Voltaria?” ou deixe sem resposta.")
    if not isinstance(tags, (list, tuple)):
        raise ValueError("Informe as tags como uma lista.")
    if len(tags) > 20:
        raise ValueError("Use no máximo 20 tags.")
    tags_limpas = []
    for tag in tags:
        tag = texto_limpo(tag, "Tag", 50).casefold()
        if tag and tag not in tags_limpas:
            tags_limpas.append(tag)
    return {
        "item_id": item_id, "data": data, "nota": normalizar_nota(nota),
        "texto": texto_limpo(texto, "Relato"), "pedido": texto_limpo(pedido, "Pedido"),
        "preco_centavos": preco_centavos,
        "voltaria": voltaria,
        "tags": tags_limpas,
    }


def raiz_busca(termo):
    """Radical simples do português para buscar por prefixo: espetinho, espetos e espeto → espet.

    Retira diminutivo, plural e vogal final, sem deixar radical curto demais, que
    traria palavras sem relação (caminho não vira "cam", bolo não vira "bol").
    Não é um stemmer completo: bolinho e bolo, por exemplo, continuam separados.
    """
    termo = termo.casefold()
    if not termo.isalpha():
        return termo
    for sufixo in DIMINUTIVOS:
        # "zinho" quase só aparece como diminutivo (pãozinho → pão); "inho" exige radical maior.
        minimo = 3 if sufixo.startswith("z") else 4
        if termo.endswith(sufixo) and len(termo) - len(sufixo) >= minimo:
            return termo[:-len(sufixo)]
    if termo.endswith("s") and len(termo) > 4:
        termo = termo[:-1]
    if termo[-1] in VOGAIS and len(termo) > 4:
        termo = termo[:-1]
    return termo


def expressao_busca(texto):
    """Converte texto livre em consulta FTS5 segura: cada palavra vira prefixo entre aspas.

    Aspas, operadores (AND, OR, NOT, NEAR), parênteses e asteriscos digitados são
    tratados como texto. Acentos e maiúsculas ficam a cargo do tokenizador da FTS.
    Retorna None quando não sobra nenhuma palavra pesquisável.
    """
    termos = TERMO.findall(texto)
    if len(termos) > MAX_TERMOS:
        raise ValueError(f"Use até {MAX_TERMOS} palavras na busca.")
    return " ".join(f'"{raiz_busca(termo)}"*' for termo in termos) or None


def preparar_busca(texto="", categoria="", nota_min="", nota_max=""):
    texto = texto_limpo(texto, "Busca", MAX_BUSCA)
    if categoria and not categoria_valida(categoria):
        raise ValueError("Categoria desconhecida.")
    nota_min, nota_max = normalizar_nota(nota_min), normalizar_nota(nota_max)
    if nota_min is not None and nota_max is not None and nota_min > nota_max:
        raise ValueError("A nota mínima ficou maior que a máxima. Inverta as duas.")
    return {"texto": texto, "expressao": expressao_busca(texto), "categoria": categoria,
            "nota_min": nota_min, "nota_max": nota_max}


def validar_chave(chave):
    if not isinstance(chave, str) or not re.fullmatch(r"[a-f0-9]{32}", chave):
        raise ValueError("O formulário expirou. Abra um novo registro.")
    return chave


def preco_em_centavos(valor):
    valor = texto_limpo(valor, "Preço", 20)
    if not valor:
        return None
    if not re.fullmatch(r"\d{1,8}(?:[.,]\d{1,2})?", valor):
        raise ValueError("Informe o preço como 12,50, sem separador de milhar.")
    return int(Decimal(valor.replace(",", ".")) * 100)


def centavos_em_texto(centavos):
    """Inverso de preco_em_centavos para preencher o formulário; desconhecido fica vazio."""
    return "" if centavos is None else f"{centavos // 100},{centavos % 100:02d}"


def validar_foto(conteudo, tipo):
    if tipo != "image/jpeg":
        raise ValueError("A foto precisa ser convertida para JPEG no navegador.")
    if not isinstance(conteudo, bytes) or not 4 <= len(conteudo) <= MAX_FOTO_BYTES:
        raise ValueError("A foto precisa ter até 768 KiB após a redução.")
    # Verificação de formato; a decodificação e a redução acontecem no navegador.
    if not conteudo.startswith(b"\xff\xd8\xff") or not conteudo.endswith(b"\xff\xd9"):
        raise ValueError("Este arquivo não parece ser uma foto JPEG.")

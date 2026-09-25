"""Regras puras: sem HTTP, banco, relógio global ou imports do Worker."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation


FUSO_LOCAL = timezone(timedelta(hours=-3))
CAMPOS_CATEGORIA = {
    "lugar": ("endereco", "bairro", "cidade"),
    "produto": ("marca", "onde_comprei", "link"),
}


def texto_limpo(valor, campo):
    if not isinstance(valor, str):
        raise ValueError(f"{campo} precisa ser texto.")
    return valor.strip()


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


def horario_local(instante):
    """O chamador fornece o relógio; o domínio só converte para o offset fixo."""
    if not isinstance(instante, datetime) or instante.utcoffset() is None:
        raise ValueError("O horário precisa informar o fuso.")
    return instante.astimezone(FUSO_LOCAL).isoformat(timespec="seconds")


def preparar_item(nome, categoria="lugar", descricao="", detalhes=None):
    nome = texto_limpo(nome, "Nome")
    if not nome:
        raise ValueError("Dê um nome para conseguir lembrar depois.")
    if not isinstance(categoria, str) or categoria not in CAMPOS_CATEGORIA:
        raise ValueError("Categoria desconhecida.")
    if detalhes is None:
        detalhes = {}
    if not isinstance(detalhes, dict):
        raise ValueError("Os detalhes precisam ser um objeto.")
    if any(campo not in CAMPOS_CATEGORIA[categoria] for campo in detalhes):
        raise ValueError("Há detalhes que não pertencem a essa categoria.")
    return {
        "nome": nome,
        "categoria": categoria,
        "descricao": texto_limpo(descricao, "Descrição"),
        "detalhes": {campo: texto_limpo(valor, campo) for campo, valor in detalhes.items()},
    }


def preparar_experiencia(
    item_id, *, hoje, data=None, nota=None, texto="", pedido="",
    preco_centavos=None, repetiria=None, tags=(),
):
    if type(item_id) is not int or item_id <= 0:
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
    if repetiria is not None and type(repetiria) is not bool:
        raise ValueError("Escolha sim, não ou deixe sem resposta.")
    if not isinstance(tags, (list, tuple)):
        raise ValueError("Informe as tags como uma lista.")
    tags_limpas = []
    for tag in tags:
        tag = texto_limpo(tag, "Tag").casefold()
        if tag and tag not in tags_limpas:
            tags_limpas.append(tag)
    return {
        "item_id": item_id, "data": data, "nota": normalizar_nota(nota),
        "texto": texto_limpo(texto, "Relato"), "pedido": texto_limpo(pedido, "Pedido"),
        "preco_centavos": preco_centavos,
        "repetiria": None if repetiria is None else int(repetiria),
        "tags": tags_limpas,
    }

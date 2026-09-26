"""Login próprio: registro da senha, sessão assinada e limite de tentativas. Sem HTTP nem banco.

A derivação PBKDF2 é injetada: `hashlib.pbkdf2_hmac` não existe nos Python Workers,
que usam o WebCrypto do runtime; testes e o script de senha usam hashlib, com o mesmo resultado.
"""

import base64
from datetime import timedelta
import hashlib
import hmac


ITERACOES = 100_000
DURACAO_SESSAO = timedelta(days=30)
MAX_FALHAS = 10
JANELA_FALHAS = timedelta(minutes=15)
MAX_SENHA = 200
MIN_SEGREDO = 32


def _b64(dados):
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _de_b64(texto):
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def formatar_registro(sal, derivada, iteracoes=ITERACOES):
    """Formato do segredo SENHA_HASH: pbkdf2_sha256$iterações$sal$hash (base64url)."""
    return f"pbkdf2_sha256${iteracoes}${_b64(sal)}${_b64(derivada)}"


def ler_registro(registro):
    try:
        algoritmo, iteracoes, sal, derivada = registro.strip().split("$")
        iteracoes, sal, derivada = int(iteracoes), _de_b64(sal), _de_b64(derivada)
    except (AttributeError, ValueError):
        raise ValueError("SENHA_HASH mal formado. Gere de novo com scripts/senha.py.") from None
    if algoritmo != "pbkdf2_sha256" or iteracoes < 1 or len(sal) < 16 or len(derivada) != 32:
        raise ValueError("SENHA_HASH mal formado. Gere de novo com scripts/senha.py.")
    return iteracoes, sal, derivada


async def senha_confere(senha, registro, derivar):
    """`derivar(senha, sal, iteracoes)` é assíncrona e devolve 32 bytes de PBKDF2-SHA256."""
    iteracoes, sal, esperada = ler_registro(registro)
    if not isinstance(senha, str) or not 0 < len(senha) <= MAX_SENHA:
        return False
    return hmac.compare_digest(await derivar(senha.encode(), sal, iteracoes), esperada)


def _assinar(segredo, expira):
    return _b64(hmac.new(segredo.encode(), f"sessao:{expira}".encode(), hashlib.sha256).digest())


def validar_segredo(segredo):
    if not isinstance(segredo, str) or len(segredo) < MIN_SEGREDO:
        raise ValueError(f"SEGREDO_SESSAO precisa ter pelo menos {MIN_SEGREDO} caracteres.")
    return segredo


def criar_sessao(segredo, instante):
    """Sessão sem estado: validade e assinatura. Trocar SEGREDO_SESSAO encerra todas as sessões."""
    expira = int((instante + DURACAO_SESSAO).timestamp())
    return f"{expira}.{_assinar(validar_segredo(segredo), expira)}"


def sessao_valida(valor, segredo, instante):
    expira, _, assinatura = (valor or "").partition(".")
    if not expira.isascii() or not expira.isdigit() or len(expira) > 12:
        return False
    return (hmac.compare_digest(assinatura, _assinar(validar_segredo(segredo), expira))
            and int(expira) > instante.timestamp())


def destino_seguro(caminho):
    """Só caminhos deste site depois do login: evita redirecionar para outro domínio."""
    if (not isinstance(caminho, str) or not caminho.startswith("/") or caminho.startswith("//")
            or "\\" in caminho or any(ord(letra) < 32 for letra in caminho) or len(caminho) > 500):
        return "/"
    return caminho

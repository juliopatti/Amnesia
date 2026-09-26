"""Gera o SENHA_HASH do login. Roda no computador, com a stdlib; nada vai para a rede.

    python3 scripts/senha.py              # pede a senha e escreve só o SENHA_HASH
    python3 scripts/senha.py --dev-vars   # grava .dev.vars para o app local

A senha não aparece na tela nem fica em arquivo; só o hash e o segredo de sessão.
"""

from getpass import getpass
import hashlib
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from acesso import ITERACOES, MAX_SENHA, formatar_registro  # noqa: E402

MIN_SENHA = 12


def pedir_senha():
    while True:
        senha = getpass("Nova senha (não aparece enquanto digita): ")
        if not MIN_SENHA <= len(senha) <= MAX_SENHA:
            print(f"Use de {MIN_SENHA} a {MAX_SENHA} caracteres. Uma frase curta serve.", file=sys.stderr)
        elif getpass("Repita a senha: ") != senha:
            print("As duas não bateram. Vamos de novo.", file=sys.stderr)
        else:
            return senha


def gerar_registro(senha):
    sal = secrets.token_bytes(16)
    return formatar_registro(sal, hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, ITERACOES))


def main():
    registro = gerar_registro(pedir_senha())
    if "--dev-vars" not in sys.argv[1:]:
        print(registro)
        return
    destino = Path(__file__).resolve().parents[1] / ".dev.vars"
    if destino.exists() and input(".dev.vars já existe. Substituir? [s/N] ").strip().lower() != "s":
        print("Nada foi alterado.", file=sys.stderr)
        return
    destino.write_text(f'SENHA_HASH="{registro}"\nSEGREDO_SESSAO="{secrets.token_urlsafe(32)}"\n')
    destino.chmod(0o600)
    print("Gravado em .dev.vars. Reinicie o app local para valer.", file=sys.stderr)


if __name__ == "__main__":
    main()

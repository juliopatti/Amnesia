"""Autoriza o amnesia no seu Google Drive e grava os segredos da publicação. Só stdlib.

    python3 scripts/google_drive.py ~/Downloads/client_secret_XXXX.json

1. Abre o navegador para você autorizar. O escopo drive.file só deixa o app ver o que ele criou.
2. Cria a pasta privada "amnesia-fotos" no seu Drive (ou reaproveita a da vez anterior).
3. Envia GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN e GOOGLE_PASTA_ID como
   segredos do Worker publicado, pelo Wrangler. Nenhum deles aparece na tela.
4. Guarda uma cópia em .google.json (ignorado pelo Git), usada para migrar as fotos locais.
"""

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
import webbrowser

RAIZ = Path(__file__).resolve().parents[1]
CONFIG = RAIZ / ".google.json"
ESCOPO = "https://www.googleapis.com/auth/drive.file"
AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
ARQUIVOS = "https://www.googleapis.com/drive/v3/files"
ENVIO = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id"


def pedir(url, dados=None, cabecalhos=None, metodo=None):
    requisicao = Request(url, data=dados, headers=cabecalhos or {}, method=metodo)
    with urlopen(requisicao, timeout=60) as resposta:
        return json.loads(resposta.read() or b"{}")


def ler_cliente(caminho):
    dados = json.loads(Path(caminho).expanduser().read_text())
    if "installed" not in dados:
        sys.exit("Esse arquivo não é de um cliente \"App para computador\". Crie um desse tipo e baixe o JSON.")
    return dados["installed"]["client_id"], dados["installed"]["client_secret"]


def autorizar(cliente_id, cliente_segredo):
    """Fluxo OAuth para apps instalados: navegador + retorno em 127.0.0.1, com PKCE."""
    verificador = secrets.token_urlsafe(64)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    estado, recebido = secrets.token_urlsafe(16), {}

    class Retorno(BaseHTTPRequestHandler):
        def do_GET(self):
            recebido.update({chave: valor[0] for chave, valor in parse_qs(urlsplit(self.path).query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Pronto. Pode fechar esta aba e voltar ao terminal.".encode())

        def log_message(self, *argumentos):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), Retorno)
    retorno = f"http://127.0.0.1:{servidor.server_port}/"
    url = AUTORIZAR + "?" + urlencode({
        "client_id": cliente_id, "redirect_uri": retorno, "response_type": "code", "scope": ESCOPO,
        "access_type": "offline", "prompt": "consent", "state": estado,
        "code_challenge": desafio, "code_challenge_method": "S256"})
    print("Abrindo o navegador. Se não abrir, copie este endereço:\n" + url + "\n")
    webbrowser.open(url)
    while "code" not in recebido and "error" not in recebido:
        servidor.handle_request()
    servidor.server_close()
    if recebido.get("error") or recebido.get("state") != estado:
        sys.exit(f"Autorização não concluída ({recebido.get('error', 'estado diferente')}).")
    tokens = pedir(TOKEN, urlencode({
        "code": recebido["code"], "client_id": cliente_id, "client_secret": cliente_segredo,
        "redirect_uri": retorno, "grant_type": "authorization_code", "code_verifier": verificador}).encode())
    if "refresh_token" not in tokens:
        sys.exit("O Google não devolveu o token de renovação. Rode o script de novo.")
    return tokens["refresh_token"], tokens["access_token"]


def token_de_acesso(config):
    return pedir(TOKEN, urlencode({
        "client_id": config["GOOGLE_CLIENT_ID"], "client_secret": config["GOOGLE_CLIENT_SECRET"],
        "refresh_token": config["GOOGLE_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode())["access_token"]


def criar_pasta(token):
    corpo = json.dumps({"name": "amnesia-fotos", "mimeType": "application/vnd.google-apps.folder"}).encode()
    return pedir(ARQUIVOS + "?fields=id", corpo,
                 {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})["id"]


def pasta_existe(token, pasta):
    try:
        return not pedir(f"{ARQUIVOS}/{pasta}?fields=trashed", cabecalhos={"Authorization": f"Bearer {token}"})["trashed"]
    except OSError:
        return False


def enviar_foto(token, pasta, chave, conteudo):
    """Mesmo formato do adaptador do Worker (src/armazenamento.py)."""
    fronteira = f"amnesia-{secrets.token_hex(16)}"
    metadados = json.dumps({"name": chave.replace("/", "-"), "parents": [pasta],
                            "mimeType": "image/jpeg", "appProperties": {"chave": chave}})
    corpo = (f"--{fronteira}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{metadados}\r\n"
             f"--{fronteira}\r\nContent-Type: image/jpeg\r\n\r\n").encode() + conteudo + f"\r\n--{fronteira}--\r\n".encode()
    return pedir(ENVIO, corpo, {"Authorization": f"Bearer {token}",
                                "Content-Type": f"multipart/related; boundary={fronteira}"})["id"]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    cliente_id, cliente_segredo = ler_cliente(sys.argv[1])
    renovacao, token = autorizar(cliente_id, cliente_segredo)
    anterior = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    pasta = anterior.get("GOOGLE_PASTA_ID")
    if not pasta or not pasta_existe(token, pasta):
        pasta = criar_pasta(token)
        print("Pasta \"amnesia-fotos\" criada no seu Drive.")
    config = {"GOOGLE_CLIENT_ID": cliente_id, "GOOGLE_CLIENT_SECRET": cliente_segredo,
              "GOOGLE_REFRESH_TOKEN": renovacao, "GOOGLE_PASTA_ID": pasta}
    CONFIG.write_text(json.dumps(config, indent=2))
    CONFIG.chmod(0o600)
    print("Enviando os segredos ao Worker publicado…")
    subprocess.run(["npx", "wrangler", "secret", "bulk", "--env", "producao"], input=json.dumps(config),
                   text=True, check=True, cwd=RAIZ)
    print("Pronto: o app publicado já guarda fotos no Drive.")


if __name__ == "__main__":
    main()

"""Copia os registros locais (.wrangler/state) para o D1 publicado e as fotos para o Drive.

    python3 scripts/migrar_dados.py

Antes: publicar o Worker, aplicar as migrações remotas e rodar scripts/google_drive.py.
O script faz uma cópia de .wrangler/state, lê os dados dessa cópia e só grava no D1
publicado se ele estiver vazio. Fotos já enviadas ficam anotadas; repetir não duplica.
"""

from datetime import datetime
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from google_drive import CONFIG, enviar_foto, token_de_acesso  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
ESTADO = RAIZ / ".wrangler/state"
ENVIADAS = RAIZ / ".wrangler/migracao-fotos.json"
SQL = RAIZ / ".wrangler/migracao-dados.sql"
# Pais antes dos filhos: o D1 confere as chaves estrangeiras.
TABELAS = ("itens", "experiencias", "tags_experiencia", "fotos")
COLUNAS_BUSCA = ("rowid", "nome", "descricao", "localizacao", "detalhes", "relatos", "pedidos", "tags")


def wrangler(*argumentos, binario=False):
    resultado = subprocess.run(["npx", "wrangler", *argumentos], cwd=RAIZ, capture_output=True, text=not binario)
    if resultado.returncode != 0:
        erro = resultado.stderr if not binario else resultado.stderr.decode(errors="replace")
        sys.exit(f"Falhou: wrangler {' '.join(argumentos[:3])}…\n{erro[-2000:]}")
    return resultado.stdout


def consultar_remoto(sql):
    saida = wrangler("d1", "execute", "amnesia", "--remote", "--env", "producao", "--json", "--command", sql)
    return json.loads(saida)[0]["results"]


def literal(valor):
    if valor is None:
        return "NULL"
    if isinstance(valor, (int, float)):
        return repr(valor)
    if isinstance(valor, bytes):
        return f"X'{valor.hex()}'"
    return "'" + str(valor).replace("'", "''") + "'"


def inserir(tabela, colunas, linhas, prefixo="INSERT INTO"):
    return [f"{prefixo} {tabela} ({', '.join(colunas)}) VALUES ({', '.join(literal(v) for v in linha)});"
            for linha in linhas]


def copiar_estado():
    copia = RAIZ / f".wrangler/state-copia-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copytree(ESTADO, copia)
    print(f"Cópia de segurança: {copia.relative_to(RAIZ)}")
    bancos = [p for p in (copia / "v3/d1/miniflare-D1DatabaseObject").glob("*.sqlite") if p.name != "metadata.sqlite"]
    if len(bancos) != 1:
        sys.exit("Não encontrei um único banco local em .wrangler/state.")
    return bancos[0]


def enviar_fotos(fotos):
    enviadas = json.loads(ENVIADAS.read_text()) if ENVIADAS.exists() else {}
    faltam = [foto for foto in fotos if foto["chave_r2"] not in enviadas]
    if not faltam:
        return enviadas
    config = json.loads(CONFIG.read_text())
    token = token_de_acesso(config)
    for numero, foto in enumerate(faltam, 1):
        conteudo = wrangler("r2", "object", "get", f"amnesia-fotos/{foto['arquivo']}", "--local", "--pipe", binario=True)
        enviadas[foto["chave_r2"]] = enviar_foto(token, config["GOOGLE_PASTA_ID"], foto["chave_r2"], conteudo)
        ENVIADAS.write_text(json.dumps(enviadas))
        print(f"Foto {numero}/{len(faltam)} enviada ao Drive.")
    return enviadas


def main():
    if not CONFIG.exists():
        sys.exit("Rode antes: python3 scripts/google_drive.py <arquivo do cliente>.json")
    if consultar_remoto("SELECT count(*) AS n FROM itens")[0]["n"]:
        sys.exit("O D1 publicado já tem itens. Nada foi alterado, para não misturar registros.")
    banco = sqlite3.connect(copiar_estado())
    banco.row_factory = sqlite3.Row
    colunas_fotos = [linha["name"] for linha in banco.execute("PRAGMA table_info(fotos)")]
    if "arquivo" not in colunas_fotos:
        sys.exit("Aplique as migrações locais antes (passo 4 do README) e rode de novo.")
    fotos = [dict(linha) for linha in banco.execute("SELECT * FROM fotos ORDER BY id")]
    enviadas = enviar_fotos(fotos)

    comandos = inserir("categorias", ("slug", "nome"), banco.execute("SELECT slug, nome FROM categorias"),
                       "INSERT OR IGNORE INTO")
    for tabela in TABELAS:
        cursor = banco.execute(f"SELECT * FROM {tabela}")
        colunas = [descricao[0] for descricao in cursor.description]
        linhas = [dict(linha) for linha in cursor]
        if tabela == "fotos":
            for linha in linhas:
                linha["arquivo"] = enviadas[linha["chave_r2"]]
        comandos += inserir(tabela, colunas, [[linha[c] for c in colunas] for linha in linhas])
    comandos += inserir("busca_itens", COLUNAS_BUSCA,
                        banco.execute(f"SELECT {', '.join(COLUNAS_BUSCA)} FROM busca_itens"))
    locais = {tabela: banco.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0] for tabela in TABELAS}
    banco.close()

    SQL.write_text("\n".join(comandos) + "\n")
    SQL.chmod(0o600)
    try:
        wrangler("d1", "execute", "amnesia", "--remote", "--env", "producao", "--file", str(SQL), "--yes")
    finally:
        SQL.unlink()
    for tabela, quantidade in locais.items():
        remota = consultar_remoto(f"SELECT count(*) AS n FROM {tabela}")[0]["n"]
        print(f"{tabela}: {quantidade} no computador, {remota} publicados")
        if remota != quantidade:
            sys.exit("As contagens não bateram. Os dados locais continuam intactos; me mostre esta saída.")
    print("Migração concluída.")


if __name__ == "__main__":
    main()

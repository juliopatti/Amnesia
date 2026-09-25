from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import unittest

from armazenamento import ArmazenamentoD1
from dominio import CATEGORIAS, campos_da_categoria, categoria_raiz, preparar_item
from paginas import formulario, formulario_item, pagina_inicial, pagina_item, valores_item
from servicos import buscar, criar_item
from dubles import BancoSQLite

AGORA = datetime(2026, 9, 25, 1, tzinfo=timezone.utc)
MIGRACOES = Path(__file__).resolve().parents[1] / "migrations"


class TestCategorias(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.binding = BancoSQLite()
        self.addCleanup(self.binding.conexao.close)
        self.banco = ArmazenamentoD1(self.binding)
        self.chaves = iter(f"{n:032x}" for n in range(1, 100))

    async def novo(self, nome, categoria, **extras):
        return await criar_item(self.banco, {"nome": nome, "categoria": categoria, **extras}, next(self.chaves), AGORA)

    async def test_banco_e_codigo_tem_as_mesmas_categorias(self):
        slugs = {linha["slug"] for linha in await self.banco.listar_categorias()}
        self.assertEqual(slugs, set(CATEGORIAS))

    async def test_cada_categoria_guarda_seus_detalhes_e_filtra(self):
        exemplos = {"restaurante": {"bairro": "Centro"}, "lugar": {"cidade": "Ouro Preto"},
                    "produto": {"marca": "Marca X"}, "filme": {"direcao": "Agnès Varda", "ano": "1962"},
                    "serie": {"criacao": "Alguém", "onde_assisti": "TV aberta"},
                    "livro": {"autoria": "Clarice Lispector", "editora": "Rocco"},
                    "musica": {"artista": "Cartola", "album": "Verde que te quero rosa"}}
        ids = {slug: await self.novo(f"Item {slug}", slug, detalhes=detalhes) for slug, detalhes in exemplos.items()}
        for slug, item_id in ids.items():
            with self.subTest(categoria=slug):
                self.assertEqual([i["id"] for i in (await buscar(self.banco, {"categoria": slug}))["itens"]], [item_id])
        self.assertEqual([i["id"] for i in (await buscar(self.banco, {"texto": "varda"}))["itens"]], [ids["filme"]])
        self.assertEqual([i["id"] for i in (await buscar(self.banco, {"texto": "clarice"}))["itens"]], [ids["livro"]])

    async def test_subcategoria_herda_campos_e_aparece_no_filtro_da_raiz(self):
        # Nenhuma subcategoria existe ainda; este teste prova que o desenho as comporta.
        self.binding.conexao.execute("INSERT INTO categorias (slug, nome) VALUES ('musica.rock', 'Rock')")
        self.assertEqual(categoria_raiz("musica.rock"), "musica")
        self.assertEqual(campos_da_categoria("musica.rock"), campos_da_categoria("musica"))
        rock = await self.novo("Disco de rock", "musica.rock", detalhes={"artista": "Rita Lee"})
        classica = await self.novo("Disco clássico", "musica", detalhes={"artista": "Villa-Lobos"})
        # Prefixo sem ponto não conta: "musica" não pode trazer um hipotético "musicais".
        todos = [i["id"] for i in (await buscar(self.banco, {"categoria": "musica"}))["itens"]]
        self.assertCountEqual(todos, [rock, classica])
        self.assertEqual([i["id"] for i in (await buscar(self.banco, {"categoria": "musica.rock"}))["itens"]], [rock])
        pagina = pagina_item(await self.banco.obter_item(rock), [])
        self.assertIn("MÚSICA", pagina)
        self.assertIn("Artista: Rita Lee", pagina)
        with self.assertRaises(ValueError):
            preparar_item("X", "musica.rock", detalhes={"marca": "Y"})


class TestFormularioCategorias(unittest.TestCase):
    def test_ids_unicos_e_campos_com_prefixo(self):
        pagina = formulario("2026-09-24", "a" * 32)
        ids = re.findall(r'\bid="([^"]+)"', pagina)
        self.assertEqual(len(ids), len(set(ids)), "ids duplicados quebram os rótulos")
        nomes = re.findall(r'\bname="([^"]+)"', pagina)
        repetidos = {nome for nome in nomes if nomes.count(nome) > 1} - {"nota", "voltaria", "acao"}
        self.assertEqual(repetidos, set(), "sem JavaScript, nomes repetidos seriam enviados juntos")
        for campo in ('name="restaurante-bairro"', 'name="lugar-bairro"', 'name="filme-direcao"',
                      'name="musica-artista"', '<option value="restaurante" selected>Bar ou restaurante'):
            self.assertIn(campo, pagina)

    def test_edicao_preenche_campos_da_categoria(self):
        item = {"id": 1, "nome": "Cléo", "categoria": "filme", "descricao": "",
                "detalhes": '{"direcao": "Agnès Varda", "ano": "1962"}'}
        valores = valores_item(item)
        self.assertEqual(valores["filme-direcao"], "Agnès Varda")
        pagina = formulario_item(item, valores)
        self.assertIn('id="filme-direcao" name="filme-direcao" type="text" value="Agnès Varda"', pagina)
        self.assertIn("Direção: Agnès Varda · Ano: 1962", pagina_item(item, []))

    def test_filtros_da_busca_mostram_todas_as_raizes(self):
        pagina = pagina_inicial()
        for categoria in CATEGORIAS.values():
            self.assertIn(f">{categoria['nome']}</label>", pagina)

    def test_ano_com_quatro_digitos(self):
        self.assertEqual(preparar_item("Livro", "livro", detalhes={"ano": "1977"})["detalhes"]["ano"], "1977")
        for ano in ("77", "mil", "19777"):
            with self.subTest(ano=ano), self.assertRaises(ValueError):
                preparar_item("Livro", "livro", detalhes={"ano": ano})


class TestMigracaoCategorias(unittest.TestCase):
    def test_lugares_antigos_viram_restaurantes_sem_perder_detalhes(self):
        banco = sqlite3.connect(":memory:")
        self.addCleanup(banco.close)
        banco.execute("PRAGMA foreign_keys = ON")
        for nome in ("0001_inicial.sql", "0002_cadastro.sql", "0003_voltaria.sql"):
            banco.executescript((MIGRACOES / nome).read_text())
        banco.execute("""INSERT INTO itens (nome, categoria, detalhes, criado_em)
                         VALUES ('Bar', 'lugar', '{"bairro": "Centro"}', 'x'), ('Café', 'produto', '{}', 'x')""")
        banco.executescript((MIGRACOES / "0004_categorias.sql").read_text())
        self.assertEqual(banco.execute("SELECT nome, categoria, detalhes FROM itens ORDER BY id").fetchall(),
                         [("Bar", "restaurante", '{"bairro": "Centro"}'), ("Café", "produto", "{}")])
        self.assertEqual({linha[0] for linha in banco.execute("SELECT slug FROM categorias")}, set(CATEGORIAS))
        self.assertEqual(banco.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()

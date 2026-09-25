from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import unittest

from dubles import ArmazenamentoMemoria, BancoD1
from armazenamento import ArmazenamentoD1
from paginas import pagina_inicial
from servicos import verificar_base


class TestServicos(unittest.IsolatedAsyncioTestCase):
    async def test_base_com_duble_sem_http(self):
        resumo = await verificar_base(ArmazenamentoMemoria(),
                                     datetime(2026, 9, 25, 1, tzinfo=timezone.utc))
        self.assertEqual(resumo["estado"], "ok")
        self.assertEqual(resumo["itens"], 2)
        self.assertEqual(resumo["experiencias"], 3)
        self.assertEqual(resumo["verificado_em"], "2026-09-24T22:00:00-03:00")

    async def test_adaptador_parametriza_sem_interpolar(self):
        banco = BancoD1([{"nome": "Bar d'Água"}])
        adaptador = ArmazenamentoD1(banco)
        parametro = "' OR 1=1 --"
        linhas = await adaptador.consultar("SELECT nome FROM itens WHERE nome = ?", (parametro,))
        self.assertEqual(banco.parametros, (parametro,))
        self.assertNotIn(parametro, banco.sql)
        self.assertEqual(linhas, [{"nome": "Bar d'Água"}])

    def test_html_escapa_dados(self):
        busca = {"texto": "<script>alert(1)</script>", "expressao": '"script"*', "categoria": "",
                 "nota_min": None, "nota_max": None}
        pagina = pagina_inicial({"busca": busca, "itens": [], "tem_mais": False})
        self.assertNotIn("<script>", pagina)
        self.assertIn("&lt;script&gt;", pagina)


class TestEsquema(unittest.TestCase):
    def setUp(self):
        self.banco = sqlite3.connect(":memory:")
        self.addCleanup(self.banco.close)
        self.banco.execute("PRAGMA foreign_keys = ON")
        caminho = Path(__file__).resolve().parents[1] / "migrations/0001_inicial.sql"
        self.banco.executescript(caminho.read_text())
        self.banco.execute("INSERT INTO itens (nome, categoria, criado_em) VALUES (?, ?, ?)",
                           ("Bar da Esquina", "lugar", "2026-09-24T20:00:00-03:00"))

    def inserir_experiencia(self, nota):
        self.banco.execute("""INSERT INTO experiencias (item_id, data, nota, criado_em)
                              VALUES (1, '2026-09-24', ?, '2026-09-24T20:00:00-03:00')""", (nota,))

    def test_banco_aceita_apenas_meias_estrelas_ou_nulo(self):
        for nota in [None] + [meia / 2 for meia in range(11)]:
            self.inserir_experiencia(nota)
        for nota in (-1, 0.1, 2.75, 5.5, "ruim"):
            with self.subTest(nota=nota), self.assertRaises(sqlite3.IntegrityError):
                self.inserir_experiencia(nota)

    def test_media_inclui_zero_e_ignora_nulo(self):
        for nota in (0, 4.5, None):
            self.inserir_experiencia(nota)
        media = self.banco.execute("SELECT avg(nota) FROM experiencias").fetchone()[0]
        self.assertEqual(media, 2.25)

    def test_fts_encontra_relato_descricao_localizacao_e_acento(self):
        self.banco.execute("""INSERT INTO busca_itens
            (rowid, nome, descricao, localizacao, detalhes, relatos, pedidos, tags)
            VALUES (1, 'Bar da Esquina', 'Balcão pequeno', 'São Paulo Pinheiros',
                    '', 'coxinha ruim', 'pastel', 'boteco')""")
        for termo in ("coxinha", "balcao", "sao", "pinheiros", "pastel", "boteco", "cox*"):
            with self.subTest(termo=termo):
                ids = self.banco.execute("SELECT rowid FROM busca_itens WHERE busca_itens MATCH ?",
                                         (termo,)).fetchall()
                self.assertEqual(ids, [(1,)])

    def test_categoria_nova_sem_alterar_tabelas(self):
        self.banco.execute("INSERT INTO categorias VALUES ('filme', 'Filmes')")
        self.banco.execute("""INSERT INTO itens (nome, categoria, detalhes, criado_em)
            VALUES ('Um filme', 'filme', '{"diretor":"Alguém"}', '2026-09-24T20:00:00-03:00')""")

    def test_integridade_detalhes_e_relacionamentos(self):
        for detalhes in ("[]", "null", "invalido"):
            with self.subTest(detalhes=detalhes), self.assertRaises(sqlite3.IntegrityError):
                self.banco.execute("UPDATE itens SET detalhes = ? WHERE id = 1", (detalhes,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.banco.execute("UPDATE itens SET categoria = 'inexistente' WHERE id = 1")
        self.inserir_experiencia(0)
        self.banco.execute("INSERT INTO tags_experiencia VALUES (1, 'bar')")
        self.banco.execute("""INSERT INTO fotos
            (experiencia_id, chave_r2, tipo_mime, tamanho_bytes)
            VALUES (1, 'foto.jpg', 'image/jpeg', 100)""")
        self.banco.execute("DELETE FROM itens WHERE id = 1")
        for tabela in ("experiencias", "tags_experiencia", "fotos"):
            self.assertEqual(self.banco.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0], 0)


class TestMigracoes(unittest.TestCase):
    def test_voltaria_converte_sim_nao_e_preserva_ausencia(self):
        banco = sqlite3.connect(":memory:")
        self.addCleanup(banco.close)
        banco.execute("PRAGMA foreign_keys = ON")
        pasta = Path(__file__).resolve().parents[1] / "migrations"
        for nome in ("0001_inicial.sql", "0002_cadastro.sql"):
            banco.executescript((pasta / nome).read_text())
        banco.execute("INSERT INTO itens (nome, categoria, criado_em) VALUES ('Bar', 'lugar', 'x')")
        for resposta in (1, 0, None):
            banco.execute("INSERT INTO experiencias (item_id, data, repetiria, criado_em) VALUES (1, '2026-01-01', ?, 'x')",
                          (resposta,))
        banco.execute("INSERT INTO tags_experiencia VALUES (1, 'bar')")
        banco.executescript((pasta / "0003_voltaria.sql").read_text())
        self.assertEqual(banco.execute("SELECT voltaria FROM experiencias ORDER BY id").fetchall(), [(4,), (1,), (None,)])
        colunas = [linha[1] for linha in banco.execute("PRAGMA table_info(experiencias)")]
        self.assertNotIn("repetiria", colunas)
        self.assertEqual(banco.execute("SELECT count(*) FROM tags_experiencia").fetchone(), (1,))
        for invalido in (6, -1):
            with self.assertRaises(sqlite3.IntegrityError):
                banco.execute("UPDATE experiencias SET voltaria = ? WHERE id = 1", (invalido,))


if __name__ == "__main__":
    unittest.main()

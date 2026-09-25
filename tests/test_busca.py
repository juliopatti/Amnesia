from datetime import datetime, timezone
import unittest

from armazenamento import ArmazenamentoD1
from paginas import pagina_inicial, url_busca
from servicos import buscar, criar_item, registrar_experiencia
from dubles import BancoSQLite

AGORA = datetime(2026, 9, 25, 1, tzinfo=timezone.utc)


class TestBusca(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.binding = BancoSQLite()
        self.addCleanup(self.binding.conexao.close)
        self.banco = ArmazenamentoD1(self.binding)
        self.chaves = iter(f"{n:032x}" for n in range(1, 1000))
        self.bar = await self.novo("Bar do Zé", descricao="Balcão de fórmica",
                                   detalhes={"bairro": "Pinheiros", "cidade": "São Paulo"})
        await self.experiencia(self.bar, texto="A coxinha estava fria.", nota=2, tags=["boteco"])
        await self.experiencia(self.bar, texto="Coxinha melhorou.", pedido="Chope", nota=3)
        self.cafe = await self.novo("Café Torrado", "produto", descricao="Açaí? Não, café.",
                                    detalhes={"marca": "Marca fictícia"})
        await self.experiencia(self.cafe, pedido="Coado", nota=0)
        self.padaria = await self.novo("Padaria sem nota", detalhes={"cidade": "Santos"})
        await self.experiencia(self.padaria, texto="Pão na chapa.")

    async def novo(self, nome, categoria="lugar", **extras):
        return await criar_item(self.banco, {"nome": nome, "categoria": categoria, **extras}, next(self.chaves), AGORA)

    async def experiencia(self, item_id, **dados):
        return await registrar_experiencia(self.banco, dados, next(self.chaves), AGORA, item_id=item_id)

    async def ids(self, **criterios):
        return [item["id"] for item in (await buscar(self.banco, criterios))["itens"]]

    async def test_coxinha_no_relato_encontra_o_bar_uma_vez(self):
        resultado = await buscar(self.banco, {"texto": "coxinha"})
        self.assertEqual([item["id"] for item in resultado["itens"]], [self.bar])
        item = resultado["itens"][0]
        self.assertIn("\x02", item["trecho"])
        self.assertEqual((item["media"], item["avaliacoes"], item["experiencias"]), (2.5, 2, 2))

    async def test_campos_pesquisaveis_sem_acento_e_maiusculas(self):
        casos = {"ze": self.bar, "FORMICA": self.bar, "chope": self.bar, "BOTECO": self.bar,
                 "pinheiros": self.bar, "sao paulo": self.bar, "acai": self.cafe,
                 "coado": self.cafe, "marca ficticia": self.cafe, "santos": self.padaria,
                 "pão chapa": self.padaria, "cox": self.bar}
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(await self.ids(texto=texto), [esperado])

    async def test_diminutivo_plural_e_singular_se_encontram(self):
        espetaria = await self.novo("Espetaria da Praça")
        await self.experiencia(espetaria, pedido="Espeto de queijo")
        boteco = await self.novo("Boteco do Tião")
        await self.experiencia(boteco, texto="Dois espetinhos e um pãozinho.")
        for texto in ("espetinho", "espeto", "espetos", "ESPETINHOS"):
            with self.subTest(texto=texto):
                self.assertCountEqual(await self.ids(texto=texto), [espetaria, boteco])
        self.assertCountEqual(await self.ids(texto="pão"), [self.padaria, boteco])

    async def test_todas_as_palavras_precisam_aparecer(self):
        self.assertEqual(await self.ids(texto="coxinha santos"), [])

    async def test_entradas_especiais_nao_quebram_a_consulta(self):
        for texto in ('"coxinha', "coxinha*", "coxinha)", "NOT coxinha", "coxinha OR café",
                      "' OR 1=1 --", "coxinha AND", "NEAR(coxinha"):
            with self.subTest(texto=texto):
                await buscar(self.banco, {"texto": texto})
        self.assertEqual(await self.ids(texto="(coxinha)"), [self.bar])

    async def test_so_simbolos_nao_lista_tudo(self):
        resultado = await buscar(self.banco, {"texto": "!!! 🍗"})
        self.assertEqual(resultado["itens"], [])
        self.assertIsNone(resultado["busca"]["expressao"])

    async def test_categoria_e_faixa_de_media(self):
        self.assertEqual(await self.ids(categoria="produto"), [self.cafe])
        self.assertEqual(await self.ids(nota_min="2.5", nota_max="2.5"), [self.bar])
        # Nota zero é avaliação; itens sem nota ficam fora quando há faixa.
        self.assertEqual(await self.ids(nota_max="1"), [self.cafe])
        self.assertEqual(await self.ids(nota_min="0"), [self.cafe, self.bar])
        self.assertEqual(await self.ids(nota_min="3"), [])
        self.assertEqual(await self.ids(), [self.padaria, self.cafe, self.bar])
        self.assertEqual(await self.ids(texto="coxinha", categoria="produto"), [])
        self.assertEqual(await self.ids(texto="coxinha", nota_min="2", categoria="lugar"), [self.bar])

    async def test_item_sem_experiencia_aparece_sem_filtro_de_nota(self):
        vazio = await self.novo("Sorveteria Esquecida")
        self.assertEqual(await self.ids(texto="sorveteria"), [vazio])
        self.assertEqual(await self.ids(texto="sorveteria", nota_min="0"), [])

    async def test_paginacao_sem_duplicar(self):
        for n in range(4):
            item = await self.novo(f"Coxinharia {n}")
            await self.experiencia(item, texto="coxinha " * 3)
        primeira = await buscar(self.banco, {"texto": "coxinha"}, 1, 3)
        segunda = await buscar(self.banco, {"texto": "coxinha"}, 2, 3)
        self.assertTrue(primeira["tem_mais"])
        self.assertFalse(segunda["tem_mais"])
        ids = [i["id"] for i in primeira["itens"] + segunda["itens"]]
        self.assertEqual(len(ids), 5)
        self.assertEqual(len(set(ids)), 5)

    async def test_filtros_invalidos(self):
        for criterios in ({"categoria": "inexistente"}, {"nota_min": "4", "nota_max": "1"}, {"nota_min": "abc"}):
            with self.subTest(criterios=criterios), self.assertRaises(ValueError):
                await buscar(self.banco, criterios)


class TestPaginaBusca(unittest.TestCase):
    def resultado(self, itens=(), texto="", expressao=None, tem_mais=False, **filtros):
        busca = {"texto": texto, "expressao": expressao, "categoria": "", "nota_min": None, "nota_max": None, **filtros}
        return {"busca": busca, "itens": list(itens), "tem_mais": tem_mais}

    def test_trecho_escapado_com_destaque(self):
        item = {"id": 1, "nome": "Bar", "categoria": "lugar", "descricao": "",
                "trecho": "<b>\x02Coxinha\x03</b> \x02solta", "media": 2.25, "experiencias": 2}
        pagina = pagina_inicial(self.resultado([item], "coxinha", '"coxinha"*'))
        self.assertIn("&lt;b&gt;<mark>Coxinha</mark>&lt;/b&gt; solta", pagina)
        self.assertNotIn("\x02", pagina)
        self.assertIn("Média 2,25 · 2 experiências", pagina)
        self.assertIn("1 item encontrado", pagina)

    def test_estados_vazios(self):
        self.assertIn("A memória começa aqui", pagina_inicial())
        sem_resultado = pagina_inicial(self.resultado(texto="<xyz>", expressao='"xyz"*'))
        self.assertIn("Nenhuma lembrança com “&lt;xyz&gt;”", sem_resultado)
        self.assertIn("Limpar busca", sem_resultado)
        self.assertIn("Só sobrou pontuação", pagina_inicial(self.resultado(texto="!!!")))
        self.assertIn("com esses filtros", pagina_inicial(self.resultado(nota_min=4.0)))
        erro = pagina_inicial(self.resultado(), erro="A nota <mínima>")
        self.assertIn('role="alert">A nota &lt;mínima&gt;', erro)

    def test_formulario_mantem_filtros_e_paginacao_preserva(self):
        busca = self.resultado(texto='bar "x"', expressao='"bar"* "x"*', tem_mais=True,
                               categoria="lugar", nota_min=3.5, nota_max=5.0)
        pagina = pagina_inicial(busca, pagina=2)
        self.assertIn('value="bar &quot;x&quot;"', pagina)
        self.assertIn('value="lugar" checked', pagina)
        self.assertIn('value="3.5" selected', pagina)
        self.assertIn('href="/?q=bar+%22x%22&amp;categoria=lugar&amp;nota_min=3.5&amp;nota_max=5&amp;pagina=3"', pagina)
        self.assertIn('nota_max=5">← Anteriores', pagina)
        self.assertEqual(url_busca(self.resultado()["busca"]), "/")


if __name__ == "__main__":
    unittest.main()

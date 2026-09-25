from datetime import datetime, timezone
import unittest

from dominio import (contato_telefone, expressao_busca, horario_local, normalizar_nota, preparar_busca,
                     preparar_experiencia, preparar_item, raiz_busca)


class TestDominio(unittest.TestCase):
    def test_todas_as_meias_estrelas_inclusive_zero(self):
        for meia in range(11):
            valor = meia / 2
            with self.subTest(valor=valor):
                self.assertEqual(normalizar_nota(valor), valor)
        self.assertEqual(normalizar_nota(" 3,5 "), 3.5)

    def test_sem_nota_e_diferente_de_zero(self):
        for vazio in (None, "", "  "):
            self.assertIsNone(normalizar_nota(vazio))
        self.assertEqual(normalizar_nota("0"), 0)

    def test_rejeita_notas_invalidas(self):
        for nota in (-0.5, 5.5, 2.3, "abc", "NaN", "Infinity", True, [], "1e99999",
                     "1.00000000000000000000000000001"):
            with self.subTest(nota=nota), self.assertRaises(ValueError):
                normalizar_nota(nota)

    def test_item_precisa_so_nome_e_preserva_descricao(self):
        item = preparar_item(" Bar da Esquina ", descricao=" Bom para conversar. ")
        self.assertEqual(item["nome"], "Bar da Esquina")
        self.assertEqual(item["descricao"], "Bom para conversar.")
        self.assertEqual(item["categoria"], "lugar")
        self.assertEqual(item["detalhes"], {})

    def test_detalhes_nao_mutam_entrada(self):
        detalhes = {"marca": " Marca X "}
        item = preparar_item("Café", "produto", detalhes=detalhes)
        self.assertEqual(item["detalhes"]["marca"], "Marca X")
        self.assertEqual(detalhes["marca"], " Marca X ")

    def test_rejeita_item_invalido(self):
        for argumentos in ({"nome": " "}, {"nome": "X", "categoria": "filme"},
                           {"nome": "X", "detalhes": []},
                           {"nome": "X", "detalhes": {"marca": "X"}}):
            with self.subTest(argumentos=argumentos), self.assertRaises(ValueError):
                preparar_item(**argumentos)

    def test_experiencia_preserva_zero_nao_e_texto_livre(self):
        exp = preparar_experiencia(1, hoje="2026-09-24", nota=0, preco_centavos=0,
                                   voltaria=0, texto=" Coxinha fria.\nNão volto. ",
                                   tags=[" Comida ", "comida", "", "Bar"])
        self.assertEqual(exp["nota"], 0)
        self.assertEqual(exp["preco_centavos"], 0)
        self.assertEqual(exp["voltaria"], 0, "Nem a pau é resposta, não ausência")
        self.assertEqual(exp["texto"], "Coxinha fria.\nNão volto.")
        self.assertEqual(exp["tags"], ["comida", "bar"])
        self.assertEqual(exp["data"], "2026-09-24")

    def test_experiencia_sem_avaliacao(self):
        exp = preparar_experiencia(1, hoje="2026-09-24")
        self.assertIsNone(exp["nota"])
        self.assertIsNone(exp["voltaria"])
        self.assertIsNone(exp["preco_centavos"])

    def test_rejeita_dados_invalidos_da_experiencia(self):
        for valores in ({"data": "2026-02-30"}, {"data": "20260924"},
                        {"preco_centavos": -1}, {"preco_centavos": 1.5},
                        {"preco_centavos": True}, {"voltaria": "sim"}, {"voltaria": 6},
                        {"voltaria": -1}, {"voltaria": True}, {"voltaria": 4.0}, {"tags": "bar"}):
            with self.subTest(valores=valores), self.assertRaises(ValueError):
                preparar_experiencia(1, hoje="2026-09-24", **valores)

    def test_expressao_busca_neutraliza_sintaxe_fts(self):
        casos = {
            "Coxinha": '"coxinh"*',
            '  açaí "do" Zé  ': '"açaí"* "do"* "zé"*',
            "NOT bar OR (cox*) -pastel NEAR/2 x:y": '"not"* "bar"* "or"* "cox"* "pastel"* "near"* "2"* "x"* "y"*',
            "happy-hour_12,50": '"happy"* "hour"* "12"* "50"*',
            "cafe\u0301": '"cafe\u0301"*',  # "é" decomposto (NFD)
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(expressao_busca(texto), esperado)
        for vazio in ("", "   ", '"*()', "🍗 !!!", "\x00\x02"):
            self.assertIsNone(expressao_busca(vazio))
        with self.assertRaises(ValueError):
            expressao_busca("a " * 11)

    def test_raiz_une_variacoes_sem_encurtar_demais(self):
        casos = {"espetinho": "espet", "Espetinhos": "espet", "espeto": "espet", "espetos": "espet",
                 "pãozinho": "pão", "cafezinho": "cafe", "pastéis": "pasté", "chope": "chop",
                 "caminho": "caminh", "cozinha": "cozinh", "bolo": "bolo", "café": "café",
                 "bar": "bar", "açaí": "açaí", "coxi": "coxi", "b12": "b12"}
        for termo, esperado in casos.items():
            with self.subTest(termo=termo):
                self.assertEqual(raiz_busca(termo), esperado)

    def test_telefone_brasileiro_internacional_e_sem_ddd(self):
        casos = {
            "(11) 98765-4321": ("tel:+5511987654321", "https://wa.me/5511987654321"),
            "011 3456.7890": ("tel:+551134567890", "https://wa.me/551134567890"),
            "+1 415 555 0100": ("tel:+14155550100", "https://wa.me/14155550100"),
            "98765-4321": ("tel:987654321", None),
            "0800 123 4567": ("tel:08001234567", None),
        }
        for telefone, (ligar, whatsapp) in casos.items():
            with self.subTest(telefone=telefone):
                self.assertEqual(contato_telefone(telefone), {"ligar": ligar, "whatsapp": whatsapp})
        for invalido in ("abc", "123", "1" * 16, "(11) 9876\n54321", "١١٩٨٧٦٥٤٣٢١", "11 98765-4321 ramal 2"):
            with self.subTest(invalido=invalido), self.assertRaises(ValueError):
                contato_telefone(invalido)
        self.assertEqual(preparar_item("Bar", detalhes={"telefone": " (11) 98765-4321 "})["detalhes"]["telefone"],
                         "(11) 98765-4321")
        with self.assertRaises(ValueError):
            preparar_item("Bar", detalhes={"telefone": "javascript:1"})
        with self.assertRaises(ValueError):
            preparar_item("Café", "produto", detalhes={"telefone": "(11) 98765-4321"})

    def test_preparar_busca_valida_filtros(self):
        busca = preparar_busca(" coxinha ", "lugar", "0", "3,5")
        self.assertEqual((busca["texto"], busca["categoria"], busca["nota_min"], busca["nota_max"]),
                         ("coxinha", "lugar", 0, 3.5))
        vazia = preparar_busca()
        self.assertEqual((vazia["expressao"], vazia["nota_min"], vazia["nota_max"]), (None, None, None))
        for argumentos in ({"categoria": "filme"}, {"nota_min": "2.3"}, {"nota_max": "6"},
                           {"nota_min": "4", "nota_max": "3"}, {"texto": "x" * 201}):
            with self.subTest(argumentos=argumentos), self.assertRaises(ValueError):
                preparar_busca(**argumentos)
        self.assertEqual(preparar_busca(nota_min="3", nota_max="3")["nota_max"], 3)

    def test_offset_fixo_na_virada_do_dia(self):
        instante = datetime(2026, 9, 25, 1, 30, tzinfo=timezone.utc)
        self.assertEqual(horario_local(instante), "2026-09-24T22:30:00-03:00")
        with self.assertRaises(ValueError):
            horario_local(datetime(2026, 9, 24))


if __name__ == "__main__":
    unittest.main()

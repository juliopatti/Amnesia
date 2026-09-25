from datetime import datetime, timezone
import unittest

from armazenamento import ArmazenamentoD1
from dominio import centavos_em_texto, preco_em_centavos
from paginas import formulario_experiencia, formulario_item, pagina_item, valores_experiencia, valores_item
from servicos import (anexar_foto, buscar, editar_experiencia, editar_item, excluir_experiencia,
                      excluir_foto, registrar_experiencia)
from dubles import ArquivosMemoria, BancoSQLite

AGORA = datetime(2026, 9, 25, 1, tzinfo=timezone.utc)
JPEG = b'\xff\xd8\xff\xe0teste\xff\xd9'


class TestEdicao(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.binding = BancoSQLite()
        self.addCleanup(self.binding.conexao.close)
        self.banco = ArmazenamentoD1(self.binding)
        self.arquivos = ArquivosMemoria()
        salvo = await registrar_experiencia(self.banco,
            {'texto': 'Coxinha fria', 'nota': 1, 'pedido': 'Chope', 'preco_centavos': 1250, 'tags': ['boteco']},
            'a' * 32, AGORA, novo_item={'nome': 'Bar Erado', 'detalhes': {'bairro': 'Centro'}})
        self.item_id, self.exp_id = salvo['item_id'], salvo['id']

    async def ids(self, texto='', **filtros):
        return [i['id'] for i in (await buscar(self.banco, {'texto': texto, **filtros}))['itens']]

    async def test_editar_item_atualiza_busca(self):
        await editar_item(self.banco, self.item_id, {'nome': 'Bar Certo', 'categoria': 'lugar',
                                                     'descricao': 'Mesa na calçada', 'detalhes': {'bairro': 'Lapa'}})
        item = await self.banco.obter_item(self.item_id)
        self.assertEqual((item['nome'], item['descricao']), ('Bar Certo', 'Mesa na calçada'))
        self.assertEqual(await self.ids('erado'), [])
        self.assertEqual(await self.ids('centro'), [])
        for termo in ('certo', 'calcada', 'lapa', 'coxinha'):
            self.assertEqual(await self.ids(termo), [self.item_id])
        self.assertEqual((await self.banco.contar_registros())['documentos_busca'], 1)

    async def test_trocar_categoria_descarta_detalhes_antigos(self):
        await editar_item(self.banco, self.item_id, {'nome': 'Bar Erado', 'categoria': 'produto',
                                                     'detalhes': {'marca': 'Marca X'}})
        self.assertEqual(await self.ids(categoria='produto'), [self.item_id])
        self.assertEqual(await self.ids('centro'), [])

    async def test_edicao_invalida_ou_inexistente_nao_altera(self):
        for dados in ({'nome': ' '}, {'nome': 'X', 'categoria': 'filme'}):
            with self.subTest(dados=dados), self.assertRaises(ValueError):
                await editar_item(self.banco, self.item_id, dados)
        with self.assertRaises(LookupError):
            await editar_item(self.banco, 999, {'nome': 'Fantasma'})
        with self.assertRaises(LookupError):
            await editar_experiencia(self.banco, 999, {}, AGORA)
        self.assertEqual((await self.banco.obter_item(self.item_id))['nome'], 'Bar Erado')

    async def test_editar_experiencia_nota_tags_e_busca(self):
        await editar_experiencia(self.banco, self.exp_id, {'texto': 'Pastel quente', 'nota': None,
            'pedido': '', 'preco_centavos': None, 'voltaria': 5, 'tags': ['Petisco', 'petisco']}, AGORA)
        exp = await self.banco.obter_experiencia(self.exp_id)
        self.assertEqual((exp['texto'], exp['nota'], exp['preco_centavos'], exp['voltaria']),
                         ('Pastel quente', None, None, 5))
        self.assertEqual(exp['data'], '2026-09-24', 'data vazia mantém a original')
        self.assertEqual(await self.banco.listar_tags(self.exp_id), ['petisco'])
        self.assertEqual(await self.ids('coxinha'), [])
        self.assertEqual(await self.ids('boteco'), [])
        self.assertEqual(await self.ids('pastel petisco'), [self.item_id])
        # Sem nota: sai de qualquer faixa de média.
        self.assertEqual(await self.ids(nota_min='0'), [])

    async def test_editar_nota_zero_e_data(self):
        await editar_experiencia(self.banco, self.exp_id, {'nota': '0', 'data': '2026-01-31'}, AGORA)
        exp = await self.banco.obter_experiencia(self.exp_id)
        self.assertEqual((exp['nota'], exp['data']), (0, '2026-01-31'))
        with self.assertRaises(ValueError):
            await editar_experiencia(self.banco, self.exp_id, {'nota': '4.2'}, AGORA)
        self.assertEqual((await self.banco.obter_experiencia(self.exp_id))['nota'], 0)

    async def test_falha_na_fts_desfaz_edicao(self):
        self.binding.falhar_em = 'INSERT INTO busca_itens'
        with self.assertRaises(RuntimeError):
            await editar_experiencia(self.banco, self.exp_id, {'texto': 'Outro', 'tags': ['nova']}, AGORA)
        with self.assertRaises(RuntimeError):
            await editar_item(self.banco, self.item_id, {'nome': 'Outro nome'})
        self.binding.falhar_em = None
        self.assertEqual((await self.banco.obter_experiencia(self.exp_id))['texto'], 'Coxinha fria')
        self.assertEqual(await self.banco.listar_tags(self.exp_id), ['boteco'])
        self.assertEqual((await self.banco.obter_item(self.item_id))['nome'], 'Bar Erado')
        self.assertEqual(await self.ids('coxinha'), [self.item_id])

    async def test_excluir_experiencia_com_fotos(self):
        foto = await anexar_foto(self.banco, self.arquivos, self.exp_id, 'b' * 32, JPEG, 'image/jpeg')
        resultado = await excluir_experiencia(self.banco, self.arquivos, self.exp_id)
        self.assertEqual(resultado, {'item_id': self.item_id, 'orfaos': 0})
        self.assertIsNone(await self.banco.obter_experiencia(self.exp_id))
        self.assertIsNone(await self.banco.obter_foto(foto['id']))
        self.assertEqual(self.arquivos.arquivos, {})
        self.assertEqual(await self.banco.consultar('SELECT * FROM tags_experiencia'), [])
        self.assertEqual(await self.ids('coxinha'), [])
        self.assertEqual(await self.ids('erado'), [self.item_id], 'o item continua')
        with self.assertRaises(LookupError):
            await excluir_experiencia(self.banco, self.arquivos, self.exp_id)

    async def test_falha_no_r2_nao_impede_exclusao(self):
        await anexar_foto(self.banco, self.arquivos, self.exp_id, 'b' * 32, JPEG, 'image/jpeg')
        self.arquivos.falhar_exclusao = True
        resultado = await excluir_experiencia(self.banco, self.arquivos, self.exp_id)
        self.assertEqual(resultado['orfaos'], 1)
        self.assertIsNone(await self.banco.obter_experiencia(self.exp_id))

    async def test_falha_no_banco_preserva_experiencia_e_fotos(self):
        await anexar_foto(self.banco, self.arquivos, self.exp_id, 'b' * 32, JPEG, 'image/jpeg')
        self.binding.falhar_em = 'INSERT INTO busca_itens'
        with self.assertRaises(RuntimeError):
            await excluir_experiencia(self.banco, self.arquivos, self.exp_id)
        self.assertIsNotNone(await self.banco.obter_experiencia(self.exp_id))
        self.assertEqual(len(await self.banco.listar_fotos(self.exp_id)), 1)
        self.assertEqual(len(self.arquivos.arquivos), 1)

    async def test_excluir_foto_libera_vaga(self):
        fotos = [await anexar_foto(self.banco, self.arquivos, self.exp_id, letra * 32, JPEG, 'image/jpeg')
                 for letra in 'bcd']
        resultado = await excluir_foto(self.banco, self.arquivos, fotos[0]['id'])
        self.assertEqual(resultado, {'experiencia_id': self.exp_id, 'orfaos': 0})
        self.assertNotIn(fotos[0]['chave_r2'], self.arquivos.arquivos)
        await anexar_foto(self.banco, self.arquivos, self.exp_id, 'e' * 32, JPEG, 'image/jpeg')
        self.assertEqual(len(await self.banco.listar_fotos(self.exp_id)), 3)
        with self.assertRaises(LookupError):
            await excluir_foto(self.banco, self.arquivos, fotos[0]['id'])


class TestFormulariosEdicao(unittest.IsolatedAsyncioTestCase):
    async def test_valores_preenchidos_e_escapados(self):
        binding = BancoSQLite()
        self.addCleanup(binding.conexao.close)
        banco = ArmazenamentoD1(binding)
        salvo = await registrar_experiencia(banco, {'texto': '</textarea><script>x</script>', 'nota': 3.5,
            'preco_centavos': 705, 'voltaria': 0, 'tags': ['a', 'b']}, 'a' * 32, AGORA,
            novo_item={'nome': '"Bar"', 'detalhes': {'cidade': '<Rio>'}})
        exp = await banco.obter_experiencia(salvo['id'])
        valores = valores_experiencia(exp, await banco.listar_tags(salvo['id']))
        self.assertEqual((valores['nota'], valores['preco'], valores['voltaria'], valores['tags']),
                         ('3.5', '7,05', '0', 'a, b'))
        pagina = formulario_experiencia(exp, valores)
        self.assertIn('id="nota-3-5" value="3.5" checked', pagina)
        self.assertIn('id="voltaria-0" value="0" checked', pagina)
        self.assertIn('Nem a pau, Juvenal!', pagina)
        self.assertNotIn('<script>x', pagina)
        item = await banco.obter_item(salvo['item_id'])
        pagina = formulario_item(item, valores_item(item))
        self.assertIn('value="&quot;Bar&quot;"', pagina)
        self.assertIn('value="&lt;Rio&gt;"', pagina)
        detalhe = pagina_item(item, await banco.listar_experiencias(item['id']))
        self.assertIn('3,5 / 5', detalhe)
        self.assertIn('&lt;Rio&gt;', detalhe)
        self.assertIn('Nenhuma experiência ainda', pagina_item(item, []))

    async def test_telefone_vira_acoes_e_entra_na_busca(self):
        binding = BancoSQLite()
        self.addCleanup(binding.conexao.close)
        banco = ArmazenamentoD1(binding)
        salvo = await registrar_experiencia(banco, {}, 'a' * 32, AGORA,
            novo_item={'nome': 'Bar', 'detalhes': {'telefone': '(11) 98765-4321'}})
        pagina = pagina_item(await banco.obter_item(salvo['item_id']), [])
        self.assertIn('href="tel:+5511987654321">Ligar · (11) 98765-4321', pagina)
        self.assertIn('href="https://wa.me/5511987654321"', pagina)
        self.assertEqual([i['id'] for i in (await buscar(banco, {'texto': '98765'}))['itens']], [salvo['item_id']])
        sem_ddd = pagina_item({'id': 1, 'nome': 'X', 'categoria': 'lugar', 'descricao': '',
                               'detalhes': '{"telefone": "9876-5432"}'}, [])
        self.assertIn('tel:98765432', sem_ddd)
        self.assertNotIn('wa.me', sem_ddd)

    def test_preco_ida_e_volta(self):
        for centavos in (None, 0, 5, 1250, 99999999):
            texto = centavos_em_texto(centavos)
            self.assertEqual(preco_em_centavos(texto), centavos)


if __name__ == '__main__':
    unittest.main()

from datetime import datetime, timezone
import unittest

from armazenamento import ArmazenamentoD1
from dominio import MAX_FOTO_BYTES, preco_em_centavos, preparar_item, validar_foto
from servicos import criar_item, registrar_experiencia, anexar_foto
from dubles import BancoSQLite, ArquivosMemoria

AGORA = datetime(2026, 9, 25, 1, tzinfo=timezone.utc)
CHAVE = 'a' * 32
JPEG = b'\xff\xd8\xff\xe0teste\xff\xd9'


class TestCadastro(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.binding = BancoSQLite()
        self.addCleanup(self.binding.conexao.close)
        self.banco = ArmazenamentoD1(self.binding)
        self.arquivos = ArquivosMemoria()

    async def registrar(self, **dados):
        return await registrar_experiencia(self.banco, dados, CHAVE, AGORA,
            novo_item={'nome': 'Bar da Esquina', 'descricao': 'Balcão pequeno',
                       'detalhes': {'bairro': 'Pinheiros', 'cidade': 'São Paulo'}})

    async def test_item_so_nome_com_indice(self):
        item = await criar_item(self.banco, {'nome': 'Café'}, CHAVE, AGORA)
        self.assertEqual((await self.banco.obter_item(item))['nome'], 'Café')
        self.assertEqual((await self.banco.contar_registros())['experiencias'], 0)
        self.assertEqual(len(await self.banco.consultar("SELECT rowid FROM busca_itens WHERE busca_itens MATCH 'cafe'")), 1)

    async def test_cadastro_completo_e_fts_atualizada(self):
        salvo = await self.registrar(nota=0, texto='Coxinha ruim', pedido='Pastel', tags=['boteco'])
        experiencia = await self.banco.obter_experiencia(salvo['id'])
        self.assertEqual(experiencia['nota'], 0)
        self.assertEqual(experiencia['data'], '2026-09-24')
        for palavra in ('coxinha', 'pastel', 'boteco', 'balcao', 'pinheiros', 'sao'):
            linhas = await self.banco.consultar('SELECT rowid FROM busca_itens WHERE busca_itens MATCH ?', (palavra,))
            self.assertEqual(linhas, [{'rowid': salvo['item_id']}])

    async def test_varias_experiencias_mantem_documento_unico(self):
        primeiro = await self.registrar(texto='coxinha')
        await registrar_experiencia(self.banco, {'texto': 'cerveja', 'nota': 4.5}, 'b'*32, AGORA, item_id=primeiro['item_id'])
        self.assertEqual(await self.banco.contar_registros(), {'itens': 1, 'experiencias': 2, 'documentos_busca': 1})
        linhas = await self.banco.consultar("SELECT rowid FROM busca_itens WHERE busca_itens MATCH 'coxinha cerveja'")
        self.assertEqual(len(linhas), 1)

    async def test_reenvio_nao_duplica_nem_altera_tags(self):
        primeiro = await self.registrar(texto='Original', tags=['primeira'])
        segundo = await self.registrar(texto='Alterado', tags=['outra'])
        self.assertEqual(primeiro, segundo)
        self.assertEqual(await self.banco.contar_registros(), {'itens': 1, 'experiencias': 1, 'documentos_busca': 1})
        self.assertEqual((await self.banco.obter_experiencia(primeiro['id']))['texto'], 'Original')
        self.assertEqual(await self.banco.consultar('SELECT tag FROM tags_experiencia'), [{'tag': 'primeira'}])

    async def test_item_avulso_reenvio_nao_duplica(self):
        primeiro = await criar_item(self.banco, {'nome': 'Café'}, CHAVE, AGORA)
        segundo = await criar_item(self.banco, {'nome': 'Outro nome'}, CHAVE, AGORA)
        self.assertEqual(primeiro, segundo)
        self.assertEqual((await self.banco.obter_item(primeiro))['nome'], 'Café')

    async def test_erro_de_validacao_nao_grava_item(self):
        with self.assertRaises(ValueError):
            await self.registrar(nota=3.2)
        self.assertEqual((await self.banco.contar_registros())['itens'], 0)

    async def test_falha_fts_desfaz_item_experiencia_e_tags(self):
        self.binding.falhar_em = 'INSERT INTO busca_itens'
        with self.assertRaises(RuntimeError):
            await self.registrar(tags=['bar'])
        self.assertEqual(await self.banco.contar_registros(), {'itens': 0, 'experiencias': 0, 'documentos_busca': 0})
        self.assertEqual(await self.banco.consultar('SELECT * FROM tags_experiencia'), [])

    async def test_item_inexistente_nao_grava(self):
        with self.assertRaises(LookupError):
            await registrar_experiencia(self.banco, {}, CHAVE, AGORA, item_id=999)

    async def test_foto_upload_e_reenvio(self):
        salvo = await self.registrar()
        foto = await anexar_foto(self.banco, self.arquivos, salvo['id'], CHAVE, JPEG, 'image/jpeg')
        novamente = await anexar_foto(self.banco, self.arquivos, salvo['id'], CHAVE, JPEG, 'image/jpeg')
        self.assertEqual(foto, novamente)
        self.assertEqual(len(self.arquivos.arquivos), 1)
        self.assertEqual(len(await self.banco.listar_fotos(salvo['id'])), 1)

    async def test_falha_upload_preserva_experiencia(self):
        salvo = await self.registrar(texto='Guardado')
        self.arquivos.falhar = True
        with self.assertRaises(OSError):
            await anexar_foto(self.banco, self.arquivos, salvo['id'], CHAVE, JPEG, 'image/jpeg')
        self.assertEqual((await self.banco.obter_experiencia(salvo['id']))['texto'], 'Guardado')
        self.assertEqual(await self.banco.listar_fotos(salvo['id']), [])

    async def test_falha_metadados_remove_objeto_orfao(self):
        salvo = await self.registrar()
        self.binding.falhar_em = 'INSERT INTO fotos'
        with self.assertRaises(RuntimeError):
            await anexar_foto(self.banco, self.arquivos, salvo['id'], CHAVE, JPEG, 'image/jpeg')
        self.assertEqual(self.arquivos.arquivos, {})
        self.assertIsNotNone(await self.banco.obter_experiencia(salvo['id']))

    async def test_limite_fotos_e_compensacao(self):
        salvo = await self.registrar()
        for letra in 'abc':
            await anexar_foto(self.banco, self.arquivos, salvo['id'], letra*32, JPEG, 'image/jpeg')
        with self.assertRaises(ValueError):
            await anexar_foto(self.banco, self.arquivos, salvo['id'], 'd'*32, JPEG, 'image/jpeg')
        self.assertEqual(len(self.arquivos.arquivos), 3)
        self.assertEqual(len(await self.banco.listar_fotos(salvo['id'])), 3)

    async def test_foto_sem_experiencia_nao_sobe(self):
        with self.assertRaises(LookupError):
            await anexar_foto(self.banco, self.arquivos, 999, CHAVE, JPEG, 'image/jpeg')
        self.assertEqual(self.arquivos.arquivos, {})


class TestEntradas(unittest.TestCase):
    def test_preco_sem_arredondamento(self):
        for entrada, esperado in (('', None), ('0', 0), ('12,50', 1250), ('12.5', 1250)):
            self.assertEqual(preco_em_centavos(entrada), esperado)
        for entrada in ('1.000,00', '-1', '0.001', 'NaN', '1e3'):
            with self.assertRaises(ValueError):
                preco_em_centavos(entrada)

    def test_link_nao_executa_script(self):
        for link in ('javascript:alert(1)', 'data:text/html,x', 'https://', 'http://['):
            with self.assertRaises(ValueError):
                preparar_item('Produto', 'produto', detalhes={'link': link})
        self.assertEqual(preparar_item('Produto', 'produto', detalhes={'link': 'https://example.com'})['detalhes']['link'], 'https://example.com')

    def test_tipo_assinatura_e_tamanho_da_foto(self):
        validar_foto(JPEG, 'image/jpeg')
        for conteudo, tipo in ((JPEG, 'image/svg+xml'), (b'<script>', 'image/jpeg'),
                              (b'x'*(MAX_FOTO_BYTES+1), 'image/jpeg')):
            with self.assertRaises(ValueError):
                validar_foto(conteudo, tipo)


if __name__ == '__main__':
    unittest.main()

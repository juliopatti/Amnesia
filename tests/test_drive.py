from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import unittest
from urllib.parse import parse_qs

from armazenamento import ArmazenamentoD1, ArmazenamentoDrive, ErroDrive
from servicos import anexar_foto, excluir_item, registrar_experiencia
from dubles import BancoSQLite

AGORA = datetime(2026, 9, 25, 1, tzinfo=timezone.utc)
JPEG = b'\xff\xd8\xff\xe0\r\n--binario\xff\xd9'
CREDENCIAIS = {'client_id': 'cliente', 'client_secret': 'segredo', 'refresh_token': 'renovacao'}


class GoogleFalso:
    """Imita as rotas de token e de arquivos usadas pelo adaptador, sem rede."""
    def __init__(self):
        self.chamadas, self.arquivos, self.forcar = [], {}, {}
        self.tokens = 0

    async def __call__(self, metodo, url, cabecalhos, corpo=None):
        self.chamadas.append((metodo, url))
        if url in self.forcar:
            return self.forcar[url]
        if url == ArmazenamentoDrive.TOKEN:
            self.tokens += 1
            self.ultimo_token_pedido = parse_qs(corpo.decode())
            return 200, json.dumps({'access_token': f'token{self.tokens}', 'expires_in': 3599}).encode()
        if cabecalhos.get('Authorization') != f'Bearer token{self.tokens}':
            return 401, b'{"error": "token velho"}'
        if url == ArmazenamentoDrive.ENVIO:
            fronteira = cabecalhos['Content-Type'].split('boundary=')[1].encode()
            partes = corpo.split(b'--' + fronteira)
            metadados = json.loads(partes[1].split(b'\r\n\r\n', 1)[1])
            conteudo = partes[2].split(b'\r\n\r\n', 1)[1][:-2]
            arquivo = f'drive{len(self.arquivos) + 1:08d}'
            self.arquivos[arquivo] = {'metadados': metadados, 'conteudo': conteudo}
            return 200, json.dumps({'id': arquivo}).encode()
        arquivo = url.removeprefix(ArmazenamentoDrive.ARQUIVOS + '/').removesuffix('?alt=media')
        if arquivo not in self.arquivos:
            return 404, b'{"error": "nao existe"}'
        if metodo == 'DELETE':
            del self.arquivos[arquivo]
            return 204, b''
        return 200, self.arquivos[arquivo]['conteudo']


class TestAdaptadorDrive(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.google, self.agora, self.cache = GoogleFalso(), 1000.0, {}
        self.drive = ArmazenamentoDrive(CREDENCIAIS, 'pasta123', self.google, lambda: self.agora, self.cache)

    async def test_envia_na_pasta_le_e_exclui(self):
        arquivo = await self.drive.salvar('experiencias/7/' + 'a' * 32 + '.jpg', JPEG)
        enviado = self.google.arquivos[arquivo]
        self.assertEqual(enviado['conteudo'], JPEG)
        self.assertEqual(enviado['metadados']['parents'], ['pasta123'])
        self.assertEqual(enviado['metadados']['appProperties'], {'chave': 'experiencias/7/' + 'a' * 32 + '.jpg'})
        self.assertNotIn('/', enviado['metadados']['name'])
        self.assertEqual(await self.drive.obter(arquivo), JPEG)
        await self.drive.excluir(arquivo)
        self.assertIsNone(await self.drive.obter(arquivo))
        await self.drive.excluir(arquivo)  # já apagado não é erro

    async def test_token_reaproveitado_e_renovado(self):
        await self.drive.salvar('a', JPEG)
        await self.drive.salvar('b', JPEG)
        self.assertEqual(self.google.tokens, 1)
        self.assertEqual(self.google.ultimo_token_pedido['grant_type'], ['refresh_token'])
        self.assertEqual(self.google.ultimo_token_pedido['refresh_token'], ['renovacao'])
        self.agora += 3599 - 30  # a menos de um minuto de expirar, pede outro
        await self.drive.salvar('c', JPEG)
        self.assertEqual(self.google.tokens, 2)

    async def test_token_recusado_antes_da_hora_e_pedido_de_novo(self):
        await self.drive.salvar('a', JPEG)
        self.cache['token'] = 'revogado'
        await self.drive.salvar('b', JPEG)
        self.assertEqual(len(self.google.arquivos), 2)

    async def test_falhas_nao_expoem_resposta(self):
        self.google.forcar[ArmazenamentoDrive.TOKEN] = (400, b'{"error": "invalid_grant", "segredo": "x"}')
        with self.assertRaisesRegex(ErroDrive, r'^Token do Google recusado \(400\)\.$'):
            await self.drive.salvar('a', JPEG)
        del self.google.forcar[ArmazenamentoDrive.TOKEN]
        self.google.forcar[ArmazenamentoDrive.ENVIO] = (403, b'{"error": "storageQuotaExceeded"}')
        with self.assertRaisesRegex(ErroDrive, r'\(403\)\.$'):
            await self.drive.salvar('a', JPEG)

    async def test_referencia_estranha_nao_vira_url(self):
        for ruim in ('../../outro', 'a b', '', None, 'x' * 5):
            with self.subTest(ruim=ruim), self.assertRaises(ErroDrive):
                await self.drive.obter(ruim)
        self.assertEqual(self.google.chamadas, [])


class CorridaNaChave:
    """Simula dois envios simultâneos: ambos acham que a foto ainda não existe."""
    def __init__(self, banco):
        self.banco, self.primeira = banco, True

    def __getattr__(self, nome):
        return getattr(self.banco, nome)

    async def foto_por_chave(self, chave):
        if self.primeira:
            self.primeira = False
            return None
        return await self.banco.foto_por_chave(chave)


class TestFotosNoDrive(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.binding = BancoSQLite()
        self.addCleanup(self.binding.conexao.close)
        self.banco = ArmazenamentoD1(self.binding)
        self.google = GoogleFalso()
        self.drive = ArmazenamentoDrive(CREDENCIAIS, 'pasta123', self.google, lambda: 0.0, {})

    async def registrar(self, chave='e' * 32):
        return await registrar_experiencia(self.banco, {'texto': 'Com foto'}, chave, AGORA,
                                           novo_item={'nome': 'Bar com foto'})

    async def test_banco_guarda_o_id_do_drive(self):
        salvo = await self.registrar()
        foto = await anexar_foto(self.banco, self.drive, salvo['id'], 'f' * 32, JPEG, 'image/jpeg')
        self.assertIn(foto['arquivo'], self.google.arquivos)
        self.assertEqual(foto['chave_r2'], f"experiencias/{salvo['id']}/{'f' * 32}.jpg")

    async def test_envio_concorrente_nao_deixa_arquivo_sobrando(self):
        salvo = await self.registrar()
        primeira = await anexar_foto(self.banco, self.drive, salvo['id'], 'f' * 32, JPEG, 'image/jpeg')
        segunda = await anexar_foto(CorridaNaChave(self.banco), self.drive, salvo['id'], 'f' * 32, JPEG, 'image/jpeg')
        self.assertEqual(segunda, primeira)
        self.assertEqual(list(self.google.arquivos), [primeira['arquivo']])

    async def test_excluir_item_apaga_arquivos_no_drive(self):
        salvo = await self.registrar()
        for letra in 'ab':
            await anexar_foto(self.banco, self.drive, salvo['id'], letra * 32, JPEG, 'image/jpeg')
        resultado = await excluir_item(self.banco, self.drive, salvo['item_id'])
        self.assertEqual(resultado['orfaos'], 0)
        self.assertEqual(self.google.arquivos, {})


class TestMigracaoArquivo(unittest.TestCase):
    def test_fotos_antigas_apontam_para_a_chave_do_r2(self):
        banco = sqlite3.connect(':memory:')
        self.addCleanup(banco.close)
        pasta = Path(__file__).resolve().parents[1] / 'migrations'
        migracoes = sorted(pasta.glob('*.sql'))
        for migracao in migracoes[:-1]:
            banco.executescript(migracao.read_text())
        self.assertEqual(migracoes[-1].name, '0006_arquivo_foto.sql')
        banco.execute("INSERT INTO itens (nome, categoria, criado_em) VALUES ('Bar', 'restaurante', 'x')")
        banco.execute("INSERT INTO experiencias (item_id, data, criado_em) VALUES (1, '2026-01-01', 'x')")
        banco.execute("""INSERT INTO fotos (experiencia_id, chave_r2, tipo_mime, tamanho_bytes)
                         VALUES (1, 'experiencias/1/abc.jpg', 'image/jpeg', 10)""")
        banco.executescript(migracoes[-1].read_text())
        self.assertEqual(banco.execute('SELECT arquivo FROM fotos').fetchall(), [('experiencias/1/abc.jpg',)])


if __name__ == '__main__':
    unittest.main()

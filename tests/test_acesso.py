from datetime import datetime, timedelta, timezone
import hashlib
import unittest

from acesso import (DURACAO_SESSAO, MAX_FALHAS, criar_sessao, destino_seguro, formatar_registro,
                    ler_registro, senha_confere, sessao_valida)
from armazenamento import ArmazenamentoD1
from paginas import pagina_entrar
from servicos import entrar
from dubles import BancoSQLite

AGORA = datetime(2026, 9, 25, 1, tzinfo=timezone.utc)
SEGREDO = "s" * 32
SAL = bytes(range(16))


async def derivar(senha, sal, iteracoes):
    """No Worker quem deriva é o WebCrypto; o resultado é o mesmo do hashlib."""
    return hashlib.pbkdf2_hmac("sha256", senha, sal, iteracoes)


def registro(senha="correta horse", iteracoes=1000):
    return formatar_registro(SAL, hashlib.pbkdf2_hmac("sha256", senha.encode(), SAL, iteracoes), iteracoes)


class TestSenha(unittest.IsolatedAsyncioTestCase):
    async def test_confere_so_a_senha_certa(self):
        self.assertTrue(await senha_confere("correta horse", registro(), derivar))
        for errada in ("Correta horse", "correta horse ", "", "x" * 201):
            with self.subTest(errada=errada):
                self.assertFalse(await senha_confere(errada, registro(), derivar))

    async def test_registro_mal_formado_e_recusado(self):
        valido = registro()
        for ruim in ("", "abc", valido.replace("pbkdf2_sha256", "md5"), valido.replace("$1000$", "$zero$"),
                     valido.rsplit("$", 1)[0] + "$curto", None):
            with self.subTest(ruim=ruim), self.assertRaises(ValueError):
                ler_registro(ruim)

    async def test_vetor_conhecido_do_pbkdf2(self):
        # RFC 7914, seção 11: garante que o formato guarda exatamente a saída do PBKDF2-SHA256.
        derivada = hashlib.pbkdf2_hmac("sha256", b"passwd", b"salt", 1, 64)
        self.assertTrue(derivada.hex().startswith("55ac046e56e3089fec1691c22544b605"))


class TestSessao(unittest.TestCase):
    def test_sessao_vale_ate_expirar(self):
        valor = criar_sessao(SEGREDO, AGORA)
        self.assertTrue(sessao_valida(valor, SEGREDO, AGORA))
        self.assertTrue(sessao_valida(valor, SEGREDO, AGORA + DURACAO_SESSAO - timedelta(seconds=1)))
        self.assertFalse(sessao_valida(valor, SEGREDO, AGORA + DURACAO_SESSAO))

    def test_sessao_adulterada_ou_de_outro_segredo(self):
        valor = criar_sessao(SEGREDO, AGORA)
        expira, assinatura = valor.split(".")
        for ruim in (f"{int(expira) + 999}.{assinatura}", f"{expira}.{assinatura[:-1]}A", "", None,
                     "abc", f"{expira}.", ".", f"-1.{assinatura}", "١٢٣.x"):
            with self.subTest(ruim=ruim):
                self.assertFalse(sessao_valida(ruim, SEGREDO, AGORA))
        self.assertFalse(sessao_valida(valor, "t" * 32, AGORA))

    def test_segredo_curto_e_recusado(self):
        with self.assertRaises(ValueError):
            criar_sessao("curto", AGORA)

    def test_destino_so_dentro_do_site(self):
        for bom in ("/", "/itens/1", "/?q=bar&categoria=filme"):
            self.assertEqual(destino_seguro(bom), bom)
        for ruim in ("https://outro.site", "//outro.site", "/\\outro.site", "itens", "/\nx", None):
            with self.subTest(ruim=ruim):
                self.assertEqual(destino_seguro(ruim), "/")

    def test_pagina_de_login_escapa_destino_e_nao_mostra_busca(self):
        pagina = pagina_entrar('/"><script>', "Senha incorreta.")
        self.assertNotIn("<script>", pagina)
        self.assertNotIn('id="q"', pagina)
        self.assertNotIn("/sair", pagina)
        self.assertIn('autocomplete="current-password"', pagina)


class TestEntrar(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.binding = BancoSQLite()
        self.addCleanup(self.binding.conexao.close)
        self.banco = ArmazenamentoD1(self.binding)

    async def tentar(self, senha, instante=AGORA):
        await entrar(self.banco, senha, registro(), derivar, instante)

    async def test_senha_errada_conta_e_acerto_limpa(self):
        for _ in range(3):
            with self.assertRaisesRegex(PermissionError, "Senha incorreta"):
                await self.tentar("errada")
        self.assertEqual(await self.banco.contar_falhas_login("2000-01-01"), 3)
        await self.tentar("correta horse")
        self.assertEqual(await self.banco.contar_falhas_login("2000-01-01"), 0)

    async def test_bloqueia_ate_a_senha_certa_depois_de_muitas_falhas(self):
        for _ in range(MAX_FALHAS):
            with self.assertRaises(PermissionError):
                await self.tentar("errada")
        with self.assertRaisesRegex(PermissionError, "Espere 15 minutos"):
            await self.tentar("correta horse")
        await self.tentar("correta horse", AGORA + timedelta(minutes=16))

    async def test_falhas_antigas_sao_apagadas(self):
        with self.assertRaises(PermissionError):
            await self.tentar("errada", AGORA - timedelta(days=1))
        with self.assertRaises(PermissionError):
            await self.tentar("errada")
        self.assertEqual(await self.banco.contar_falhas_login("2000-01-01"), 1)


if __name__ == "__main__":
    unittest.main()

// Entra uma vez com a senha fictícia dos testes e guarda o cookie para todos os cenários.
const { request } = require('@playwright/test');

const origem = 'http://127.0.0.1:8790';

module.exports = async () => {
  const contexto = await request.newContext({ baseURL: origem });
  const resposta = await contexto.post('/entrar', {
    form: { senha: 'senha-de-teste-e2e', volta: '/' }, headers: { Origin: origem }, maxRedirects: 0,
  });
  if (resposta.status() !== 303) throw new Error(`Login dos testes falhou: ${resposta.status()}`);
  await contexto.storageState({ path: '.wrangler/test-state/sessao-e2e.json' });
  await contexto.dispose();
};

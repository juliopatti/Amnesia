// Grava docs/demo.gif: sobe o app num banco isolado, com dados fictícios, e filma um
// cadastro, a busca e a página do item. Uso: npm run demo
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { chromium, devices } = require('@playwright/test');
const ffmpeg = require('@ffmpeg-installer/ffmpeg').path;

const RAIZ = path.resolve(__dirname, '..');
const ESTADO = path.join(RAIZ, '.wrangler', 'demo-state');
const GIF = path.join(RAIZ, 'docs', 'demo.gif');
const PORTA = 8791;
const ORIGEM = `http://127.0.0.1:${PORTA}`;
// Senha e segredo fictícios, os mesmos dos testes de navegador (playwright.config.cjs).
const SENHA = 'senha-de-teste-e2e';
const SENHA_HASH = 'pbkdf2_sha256$1000$YW1uZXNpYS1lMmUtc2FsIQ$piZL9wuN6ZkHFv-5vwfR9W4ASiJKNoIdlxk6f0V3N_k';
const SEGREDO_SESSAO = 'segredo-de-sessao-dos-testes-e2e-0000';
const TELA = { width: 412, height: 780 };

function executar(comando, argumentos) {
  const resultado = spawnSync(comando, argumentos, { cwd: RAIZ, encoding: 'utf8' });
  if (resultado.error || resultado.status !== 0) {
    throw new Error(`${comando} falhou: ${resultado.error?.message || resultado.stderr}`);
  }
}

async function ligarApp() {
  fs.rmSync(ESTADO, { recursive: true, force: true });
  executar('uv', ['run', 'pywrangler', 'd1', 'migrations', 'apply', 'amnesia', '--local', '--persist-to', ESTADO]);
  // Grupo de processos próprio: o Wrangler abre filhos, e todos precisam sair no final.
  const app = spawn('uv', ['run', 'pywrangler', 'dev', '--ip', '127.0.0.1', '--port', String(PORTA),
    '--persist-to', ESTADO, '--var', `SENHA_HASH:${SENHA_HASH}`, '--var', `SEGREDO_SESSAO:${SEGREDO_SESSAO}`],
  { cwd: RAIZ, detached: true, stdio: 'ignore' });
  for (let tentativa = 0; tentativa < 60; tentativa += 1) {
    try {
      if ((await fetch(`${ORIGEM}/saude`)).ok) return app;
    } catch { /* ainda subindo */ }
    await new Promise((resolver) => setTimeout(resolver, 2000));
  }
  desligarApp(app);
  throw new Error('O app local não respondeu em 2 minutos.');
}

function desligarApp(app) {
  try { process.kill(-app.pid, 'SIGTERM'); } catch { /* já saiu */ }
}

async function registrar(page, { categoria, nome, nota, relato }) {
  await page.goto('/registrar');
  if (categoria) await page.getByLabel('O que é?').selectOption(categoria);
  await page.getByLabel('Nome', { exact: true }).fill(nome);
  await page.locator(`label[for="nota-${nota}"]`).click();
  await page.getByLabel('Como foi?').fill(relato);
  await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
  await page.waitForURL(/\/experiencias\/\d+/);
}

// Fora da gravação: entra e deixa três registros para a lista não aparecer vazia.
async function preparar(navegador, opcoes) {
  const contexto = await navegador.newContext(opcoes);
  const page = await contexto.newPage();
  await page.goto('/entrar');
  await page.getByLabel('Senha').fill(SENHA);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.waitForURL(`${ORIGEM}/`);
  await registrar(page, { nome: 'Pastelaria da Praça', nota: '4-5', relato: 'Pastel de queijo honesto e caldo de cana gelado.' });
  await registrar(page, { categoria: 'produto', nome: 'Fone sem fio genérico', nota: '2', relato: 'A bateria durou uma semana.' });
  await registrar(page, { categoria: 'filme', nome: 'Filme de domingo', nota: '3-5', relato: 'Dormi no meio, mas o começo era bom.' });
  const sessao = await contexto.storageState();
  await contexto.close();
  return sessao;
}

async function filmar(navegador, opcoes, sessao, pasta) {
  const contexto = await navegador.newContext({ ...opcoes, storageState: sessao, recordVideo: { dir: pasta, size: TELA } });
  const page = await contexto.newPage();
  const pausa = (ms) => page.waitForTimeout(ms);
  const digitar = (alvo, texto) => alvo.pressSequentially(texto, { delay: 38 });

  await page.goto('/');
  await pausa(1800);
  await page.getByRole('link', { name: '+ Registrar experiência' }).click();
  await pausa(900);
  await digitar(page.getByLabel('Nome', { exact: true }), 'Boteco do Zé');
  await pausa(300);
  await page.locator('label[for="nota-1-5"]').click();
  await pausa(600);
  await digitar(page.getByLabel('Como foi?'), 'Coxinha fria. Não volto.');
  await pausa(400);
  await page.getByText('Mais detalhes', { exact: false }).click();
  await pausa(500);
  await digitar(page.getByLabel('O que pedi ou provei'), 'Coxinha e chope');
  await digitar(page.getByLabel('Quanto paguei (R$)'), '18,50');
  await page.locator('label[for="voltaria-0"]').click();
  await pausa(600);
  await digitar(page.getByLabel('Tags'), 'coxinha, happy hour');
  await digitar(page.locator('#restaurante-endereco'), 'Rua das Flores, 123');
  await digitar(page.locator('#restaurante-bairro'), 'Setor Central');
  await digitar(page.locator('#restaurante-cidade'), 'Goiânia');
  await digitar(page.locator('#restaurante-telefone'), '(62) 99999-0000');
  await pausa(700);
  await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
  await page.waitForURL(/\/experiencias\/\d+/);
  await pausa(2200);
  await page.goto('/');
  await pausa(900);
  await page.getByLabel('Buscar nas lembranças').pressSequentially('coxinha', { delay: 100 });
  await pausa(2000);
  await page.locator('.nome-item').first().click();
  await pausa(1800);
  await page.getByRole('link', { name: 'WhatsApp' }).hover();
  await pausa(3000);

  const video = page.video();
  await contexto.close();
  return video.path();
}

function converter(video) {
  const filtro = 'fps=10,scale=360:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];'
    + '[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle';
  fs.chmodSync(ffmpeg, 0o755);
  executar(ffmpeg, ['-v', 'error', '-y', '-i', video, '-vf', filtro, GIF]);
}

async function main() {
  const pasta = fs.mkdtempSync(path.join(os.tmpdir(), 'amnesia-demo-'));
  const app = await ligarApp();
  const executavel = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  const navegador = await chromium.launch(executavel ? { executablePath: executavel } : {});
  try {
    const opcoes = { ...devices['Pixel 7'], viewport: TELA, baseURL: ORIGEM };
    const sessao = await preparar(navegador, opcoes);
    converter(await filmar(navegador, opcoes, sessao, pasta));
    console.log('Gerado: docs/demo.gif');
  } finally {
    await navegador.close();
    desligarApp(app);
    fs.rmSync(pasta, { recursive: true, force: true });
  }
}

main().catch((erro) => {
  console.error(erro.message);
  process.exit(1);
});

const { test, expect } = require('@playwright/test');
const { randomUUID } = require('node:crypto');

const nomeUnico = prefixo => `${prefixo} ${randomUUID().slice(0, 8)}`;
const origem = 'http://127.0.0.1:8790';
const errosPagina = [];

test.beforeEach(async ({ page }) => {
  errosPagina.length = 0;
  page.on('pageerror', erro => errosPagina.push(erro.message));
});
test.afterEach(async () => { expect(errosPagina).toEqual([]); });

async function fotoPNG(page) {
  const dados = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 2200; canvas.height = 1800;
    const contexto = canvas.getContext('2d');
    contexto.fillStyle = '#31533e'; contexto.fillRect(0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  return { name: 'foto-teste.png', mimeType: 'image/png', buffer: Buffer.from(dados, 'base64') };
}

test('cadastro rápido, meia estrela, teclado e nova experiência no mesmo item', async ({ page }) => {
  const nome = nomeUnico('Bar de teste');
  await page.goto('/');
  await page.getByRole('link', { name: '+ Registrar experiência' }).click();
  await page.getByLabel('Nome', { exact: true }).fill(nome);
  await page.locator('label[for="nota-2-5"]').click();
  await expect(page.locator('.nota-atual')).toHaveText('2,5 / 5');
  await page.locator('#nota-2-5').focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('.nota-atual')).toHaveText('3 / 5');
  await page.keyboard.press('ArrowLeft');
  await page.getByLabel('Como foi?').fill('Coxinha fria.\nNão volto.');
  const inicio = Date.now();
  await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
  await expect(page).toHaveURL(/\/experiencias\/\d+$/);
  expect(Date.now() - inicio).toBeLessThan(10000);
  await expect(page.locator('.resumo')).toContainText(nome);
  await expect(page.locator('.resumo')).toContainText('2,5 / 5');
  await page.getByRole('link', { name: 'Outra experiência aqui' }).click();
  await expect(page.locator('.item-escolhido')).toContainText(nome);
  await page.getByLabel('0 estrelas', { exact: true }).check();
  await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
  await expect(page.locator('.resumo')).toContainText('0 / 5');
});

test('produto, campos extras, validação preserva texto e filtro htmx', async ({ page }) => {
  const nome = nomeUnico('Café de teste');
  await page.goto('/registrar');
  await page.getByLabel('O que é?').selectOption('produto');
  await page.getByLabel('Nome', { exact: true }).fill(nome);
  await page.getByLabel('Como foi?').fill('Amargo na medida.');
  await page.getByText('Mais detalhes', { exact: false }).click();
  await page.getByLabel('Sobre o lugar ou produto').fill('Torra escura.');
  await page.getByLabel('Marca', { exact: true }).fill('Marca fictícia');
  await page.getByLabel('Quanto paguei (R$)').fill('12,345');
  await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('12,50');
  await expect(page.getByLabel('Como foi?')).toHaveValue('Amargo na medida.');
  await page.getByLabel('Quanto paguei (R$)').fill('12,50');
  await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
  await expect(page).toHaveURL(/\/experiencias\/\d+$/);
  await page.goto('/');
  const resposta = page.waitForRequest(req => req.url().includes('categoria=produto') && req.headers()['hx-request'] === 'true');
  await page.getByRole('link', { name: 'Produtos', exact: true }).click();
  await resposta;
  await expect(page.locator('.itens')).toContainText(nome);
  await expect(page.locator('.itens')).toContainText('Torra escura.');
});

test('item avulso funciona sem JavaScript e conteúdo é escapado', async ({ browser }) => {
  const contexto = await browser.newContext({ javaScriptEnabled: false, baseURL: origem, viewport: { width: 390, height: 844 } });
  const page = await contexto.newPage();
  try {
    await page.goto('/registrar');
    const nome = nomeUnico('<script>alert(1)</script>');
    await page.getByLabel('Nome', { exact: true }).fill(nome);
    await page.getByRole('button', { name: 'Só guardar o item, sem experiência' }).click();
    await expect(page).toHaveURL(/\/itens\/\d+$/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(nome);
    await page.getByRole('link', { name: 'Registrar uma experiência', exact: true }).click();
    await page.getByLabel('Como foi?').fill('Registro sem JavaScript.');
    await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
    await expect(page.locator('.resumo')).toContainText('Registro sem JavaScript.');
    await expect(page.locator('.resumo')).toContainText('Sem nota');
  } finally { await contexto.close(); }
});

test('foto reduzida, falha de upload preserva registro e permite repetir', async ({ page }) => {
  await page.goto('/registrar');
  await page.getByLabel('Nome', { exact: true }).fill(nomeUnico('Bar com foto'));
  await page.getByLabel('Como foi?').fill('Texto salvo antes da foto.');
  await page.locator('#fotos').setInputFiles(await fotoPNG(page));
  await expect(page.locator('#previas')).toContainText('KiB');
  await page.route('**/uploads/*', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"erro":"Falha simulada no upload"}' }));
  await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
  await expect(page.locator('#resultado-upload')).toContainText('Seu registro está salvo');
  const destino = await page.getByRole('link', { name: 'Continuar com o registro salvo' }).getAttribute('href');
  const salvo = await page.request.get(destino);
  expect(await salvo.text()).toContain('Texto salvo antes da foto.');
  await page.unroute('**/uploads/*');
  const upload = page.waitForRequest('**/uploads/*');
  await page.getByRole('button', { name: 'Tentar fotos novamente' }).click();
  const request = await upload;
  expect(request.headers()['content-type']).toBe('image/jpeg');
  await expect(page).toHaveURL(/\/experiencias\/\d+$/);
  const imagem = page.locator('.galeria img');
  await expect(imagem).toBeVisible();
  await expect.poll(() => imagem.evaluate(img => img.naturalWidth)).toBe(1600);
  const foto = await page.request.get(await imagem.getAttribute('src'));
  expect((await foto.body()).length).toBeLessThanOrEqual(768 * 1024);
  expect(foto.headers()['content-type']).toBe('image/jpeg');
  expect(foto.headers()['x-content-type-options']).toBe('nosniff');
});

test('POST externo é bloqueado e reenvio concorrente é idempotente', async ({ page, request }) => {
  await page.goto('/registrar');
  const chave = await page.locator('input[name="chave"]').inputValue();
  const form = { chave, nome: nomeUnico('Idempotente'), categoria: 'lugar', nota: '0.5', texto: 'Não duplicar', acao: 'experiencia' };
  const externo = await request.post('/registros', { form, headers: { Origin: 'https://outro.example' } });
  expect(externo.status()).toBe(403);
  const respostas = await Promise.all([1, 2].map(() => request.post('/registros', { form, headers: { Origin: origem, Accept: 'application/json' } })));
  expect(respostas.every(r => r.ok())).toBeTruthy();
  expect(await respostas[0].json()).toEqual(await respostas[1].json());
  const invalida = await request.post('/uploads/999999', {
    data: '<svg onload="alert(1)">', headers: { Origin: origem, 'Content-Type': 'image/svg+xml', 'X-Chave-Foto': chave },
  });
  expect(invalida.status()).toBe(400);
});

test('layout mobile sem rolagem horizontal e controles rotulados', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto('/registrar');
  await expect(page.getByRole('heading', { name: 'Guardar uma experiência' })).toBeVisible();
  const tamanho = await page.evaluate(() => ({ largura: document.documentElement.scrollWidth, janela: innerWidth }));
  expect(tamanho.largura).toBeLessThanOrEqual(tamanho.janela);
  const semRotulo = await page.locator('input:not([type=hidden]), select, textarea').evaluateAll(campos => campos.filter(c => !c.labels?.length).map(c => c.id));
  expect(semRotulo).toEqual([]);
  await page.screenshot({ path: 'test-results/cadastro-mobile.png', fullPage: true });
});

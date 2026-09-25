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
  await expect(page).toHaveURL(/\/experiencias\/\d+(\?guardada=1)?$/);
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
  await page.getByLabel('Descrição').fill('Torra escura.');
  await page.getByLabel('Marca', { exact: true }).fill('Marca fictícia');
  await page.getByLabel('Quanto paguei (R$)').fill('12,345');
  await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('12,50');
  await expect(page.getByLabel('Como foi?')).toHaveValue('Amargo na medida.');
  await page.getByLabel('Quanto paguei (R$)').fill('12,50');
  await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
  await expect(page).toHaveURL(/\/experiencias\/\d+(\?guardada=1)?$/);
  await page.goto('/');
  const resposta = page.waitForRequest(req => req.url().includes('categoria=produto') && req.headers()['hx-request'] === 'true');
  await page.getByText('Produtos', { exact: true }).click();
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
    await page.getByRole('link', { name: 'Editar experiência' }).click();
    await expect(page.getByLabel('Como foi?')).toHaveValue('Registro sem JavaScript.');
    await page.getByLabel('Como foi?').fill('Editado sem JavaScript.');
    await page.getByLabel('2 estrelas', { exact: true }).check();
    await page.getByRole('button', { name: 'Guardar alterações' }).click();
    await expect(page.locator('.resumo')).toContainText('Editado sem JavaScript.');
    await expect(page.locator('.resumo')).toContainText('2 / 5');
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
  await expect(page).toHaveURL(/\/experiencias\/\d+(\?guardada=1)?$/);
  const imagem = page.locator('.galeria img');
  await expect(imagem).toBeVisible();
  await expect.poll(() => imagem.evaluate(img => img.naturalWidth)).toBe(1600);
  const foto = await page.request.get(await imagem.getAttribute('src'));
  expect((await foto.body()).length).toBeLessThanOrEqual(768 * 1024);
  expect(foto.headers()['content-type']).toBe('image/jpeg');
  expect(foto.headers()['x-content-type-options']).toBe('nosniff');
  const endereco = await imagem.getAttribute('src');
  const experiencia = page.url();
  await page.getByRole('link', { name: '← Todas as experiências' }).click();
  await expect(page.locator('.experiencias .miniatura')).toHaveAttribute('src', endereco);
  await page.goto(experiencia);
  await page.getByRole('link', { name: 'Remover foto 1' }).click();
  await expect(page.getByRole('heading', { name: 'Remover esta foto?' })).toBeVisible();
  await page.getByRole('button', { name: 'Excluir de vez' }).click();
  await expect(page).toHaveURL(/\/experiencias\/\d+(\?guardada=1)?$/);
  await expect(page.locator('.galeria img')).toHaveCount(0);
  await expect(page.locator('.resumo')).toContainText('Texto salvo antes da foto.');
  expect((await page.request.get(endereco)).status()).toBe(404);
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

test('busca no topo encontra relato, ignora acento, filtra e trata entradas especiais', async ({ page }) => {
  const marcador = randomUUID().slice(0, 8).replace(/^\d/, 'b');
  const nome = `Bar da busca ${marcador}`;
  await page.goto('/registrar');
  await page.getByLabel('Nome', { exact: true }).fill(nome);
  await page.locator('label[for="nota-4"]').click();
  await page.getByLabel('Como foi?').fill('Coxinha crocante. Açaí nem tanto.');
  await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
  await expect(page).toHaveURL(/\/experiencias\/\d+(\?guardada=1)?$/);
  await page.getByRole('link', { name: 'Outra experiência aqui' }).click();
  await page.getByLabel('Como foi?').fill('Voltei pela coxinha.');
  await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
  await expect(page).toHaveURL(/\/experiencias\/\d+(\?guardada=1)?$/);

  // Busca digitada em outra página leva à inicial.
  await page.getByLabel('Buscar nas lembranças').fill(`COXINHA ${marcador}`);
  await page.getByLabel('Buscar nas lembranças').press('Enter');
  await expect(page).toHaveURL(/\/\?q=COXINHA/);
  await expect(page.locator('.item')).toHaveCount(1);
  await expect(page.locator('.item mark').first()).toHaveText(/coxinha/i);
  await expect(page.locator('.item')).toContainText('Média 4 · 2 experiências');

  const campo = page.getByLabel('Buscar nas lembranças');
  const htmx = () => page.waitForResponse(r => r.url().includes('/?') && r.request().headers()['hx-request'] === 'true');
  let resposta = htmx();
  await campo.fill(`acai ${marcador}`);
  await resposta;
  await expect(page.locator('.item')).toHaveCount(1);
  await expect(page.locator('.item')).toContainText(nome);
  await expect(page.getByRole('status')).toHaveText('1 lembrança resgatada');

  resposta = htmx();
  await page.getByLabel('Média de').selectOption('4.5');
  await resposta;
  await expect(page.locator('.vazio')).toContainText('Nenhuma lembrança com');
  await expect(page).toHaveURL(/nota_min=4\.5/);

  resposta = htmx();
  await page.getByLabel('até', { exact: true }).selectOption('1');
  expect((await resposta).status()).toBe(422);
  await expect(page.getByRole('alert')).toContainText('mínima ficou maior');
  await expect(campo).toHaveValue(`acai ${marcador}`);

  await page.goto('/?q=%22*()%20%F0%9F%8D%97');
  await expect(page.locator('.vazio')).toContainText('Só sobrou pontuação');
  for (const especial of ['"NOT (coxinha', "' OR 1=1 --", 'NEAR/2 *']) {
    const pagina = await page.request.get(`/?q=${encodeURIComponent(especial)}`);
    expect(pagina.status()).toBe(200);
  }
  await page.goto(`/?q=coxinha+${marcador}&categoria=produto`);
  await expect(page.locator('.vazio')).toContainText('Nenhuma lembrança');
  await page.getByRole('link', { name: 'Limpar busca' }).click();
  await expect(page.getByRole('heading', { name: /Foi bom\?/ })).toBeVisible();
});

test('edita item e experiência, reflete na busca e exclui com confirmação', async ({ page }) => {
  const marcador = randomUUID().slice(0, 8).replace(/^\d/, 'b');
  await page.goto('/registrar');
  await page.getByLabel('Nome', { exact: true }).fill(`Bar erado ${marcador}`);
  await page.locator('label[for="nota-2"]').click();
  await page.getByLabel('Como foi?').fill('Coxinha fria.');
  await page.getByText('Mais detalhes', { exact: false }).click();
  await page.getByLabel('Tags').fill('boteco');
  await page.getByLabel('Quanto paguei (R$)').fill('7,05');
  await page.getByRole('button', { name: 'Guardar experiência', exact: true }).click();
  await expect(page).toHaveURL(/\/experiencias\/\d+(\?guardada=1)?$/);
  const experiencia = page.url().split('?')[0];

  await page.getByRole('link', { name: 'Editar experiência' }).click();
  await expect(page.getByLabel('Como foi?')).toHaveValue('Coxinha fria.');
  await expect(page.getByLabel('Tags')).toHaveValue('boteco');
  await expect(page.getByLabel('Quanto paguei (R$)')).toHaveValue('7,05');
  await expect(page.locator('.nota-atual')).toHaveText('2 / 5');
  await page.locator('label[for="nota-4-5"]').click();
  await page.getByLabel('Como foi?').fill('Espetinho no ponto.');
  await page.getByLabel('Quanto paguei (R$)').fill('7,555');
  await page.getByRole('button', { name: 'Guardar alterações' }).click();
  await expect(page.getByRole('alert')).toContainText('12,50');
  await expect(page.getByLabel('Como foi?')).toHaveValue('Espetinho no ponto.');
  await page.getByLabel('Quanto paguei (R$)').fill('');
  await page.getByText('Nem a pau, Juvenal!').click();
  await page.getByRole('button', { name: 'Guardar alterações' }).click();
  await expect(page).toHaveURL(experiencia);
  await expect(page.locator('.resumo')).toContainText('Voltaria? Nem a pau, Juvenal!');
  await page.getByRole('link', { name: 'Editar experiência' }).click();
  await expect(page.getByLabel('Nem a pau, Juvenal!')).toBeChecked();
  await page.getByLabel('Sem resposta').check();
  await page.getByRole('button', { name: 'Guardar alterações' }).click();
  await expect(page.locator('.resumo')).not.toContainText('Voltaria?');
  await expect(page.locator('.resumo')).toContainText('4,5 / 5');
  await expect(page.locator('.resumo')).toContainText('Espetinho no ponto.');

  await page.getByRole('link', { name: '← Todas as experiências' }).click();
  await page.getByRole('link', { name: 'Editar item' }).click();
  await expect(page.getByLabel('Nome', { exact: true })).toHaveValue(`Bar erado ${marcador}`);
  await page.getByLabel('O que é?').selectOption('produto');
  await page.locator('#produto-link').fill('javascript:alert(1)');
  await page.getByRole('button', { name: 'Guardar alterações' }).click();
  await expect(page.getByRole('alert')).toContainText('http://');
  await page.getByLabel('O que é?').selectOption('restaurante');
  await page.getByLabel('Nome', { exact: true }).fill(`Bar certo ${marcador}`);
  await page.locator('#restaurante-bairro').fill('Lapa');
  await page.locator('#restaurante-telefone').fill('(11) 98765-4321');
  await page.getByRole('button', { name: 'Guardar alterações' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(`Bar certo ${marcador}`);
  await expect(page.getByRole('link', { name: 'WhatsApp' })).toHaveAttribute('href', 'https://wa.me/5511987654321');
  await expect(page.getByRole('link', { name: /^Ligar/ })).toHaveAttribute('href', 'tel:+5511987654321');
  await expect(page.locator('.experiencias')).toContainText('4,5 / 5');
  await expect(page.locator('.media-item')).toContainText('4,5');
  await expect(page.locator('.media-item').getByRole('img', { name: '4,5 de 5' })).toBeVisible();
  await expect(page.locator('.resumo-voltaria')).toHaveCount(0);

  for (const [termo, total] of [[`erado ${marcador}`, 0], [`espeto ${marcador}`, 1], [`coxinha ${marcador}`, 0], [`lapa ${marcador}`, 1]]) {
    await page.goto(`/?q=${encodeURIComponent(termo)}`);
    await expect(page.locator('.item'), termo).toHaveCount(total);
  }

  await page.goto(experiencia);
  await page.getByRole('link', { name: 'Excluir', exact: true }).click();
  await page.getByRole('link', { name: 'Melhor não' }).click();
  await expect(page).toHaveURL(experiencia);
  await page.getByRole('link', { name: 'Excluir', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Excluir esta experiência?' })).toBeVisible();
  await page.getByRole('button', { name: 'Excluir de vez' }).click();
  await expect(page).toHaveURL(/\/itens\/\d+$/);
  await expect(page.locator('.experiencias')).toContainText('Nenhuma experiência ainda');
  expect((await page.request.get(experiencia)).status()).toBe(404);
  await page.goto(`/?q=espetinho+${marcador}`);
  await expect(page.locator('.item')).toHaveCount(0);
});

test('categorias novas: filme com detalhes próprios e filtro por categoria', async ({ page }) => {
  const nome = nomeUnico('Filme de teste');
  await page.goto('/registrar');
  await expect(page.getByLabel('Nome', { exact: true })).toHaveAttribute('placeholder', 'Aquele bar da esquina…');
  await page.getByLabel('O que é?').selectOption('filme');
  await expect(page.getByLabel('Nome', { exact: true })).toHaveAttribute('placeholder', 'Aquele em que você dormiu no meio…');
  await expect(page.getByLabel('Como foi?')).toHaveAttribute('placeholder', 'Dormi no meio. Acordei no final. Não perdi nada.');
  await page.getByLabel('Nome', { exact: true }).fill(nome);
  await page.getByText('Mais detalhes', { exact: false }).click();
  await expect(page.locator('#filme-direcao')).toBeVisible();
  await expect(page.locator('#restaurante-bairro')).toBeHidden();
  await page.locator('#filme-direcao').fill('Diretora Fictícia');
  await page.locator('#filme-ano').fill('1962');
  await page.getByRole('button', { name: 'Só guardar o item, sem experiência' }).click();
  await expect(page.getByText('Direção: Diretora Fictícia · Ano: 1962')).toBeVisible();
  await expect(page.locator('.sobretitulo')).toHaveText('FILME');
  await page.goto('/');
  const resposta = page.waitForResponse(r => r.url().includes('categoria=filme') && r.request().headers()['hx-request'] === 'true');
  await page.getByText('Filmes', { exact: true }).click();
  await resposta;
  await expect(page.locator('.itens')).toContainText(nome);
  await expect(page.locator('.itens')).not.toContainText('Bar de teste');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Filmes');
  await page.getByRole('link', { name: '+ Registrar experiência' }).click();
  await expect(page).toHaveURL(/\/registrar\?categoria=filme$/);
  await expect(page.getByLabel('O que é?')).toHaveValue('filme');
  await expect(page.getByLabel('Como foi?')).toHaveAttribute('placeholder', 'Dormi no meio. Acordei no final. Não perdi nada.');
  await page.goto('/registrar?categoria=%3Cscript%3E');
  await expect(page.getByLabel('O que é?')).toHaveValue('restaurante');
});

test('no computador todas as categorias aparecem sem rolagem', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/');
  const faixa = await page.locator('.filtros').boundingBox();
  for (const nome of ['Tudo', 'Bares e restaurantes', 'Livros', 'Música']) {
    const pilula = await page.getByText(nome, { exact: true }).boundingBox();
    expect(pilula.x + pilula.width, nome).toBeLessThanOrEqual(faixa.x + faixa.width);
  }
  expect(await page.locator('.filtros').evaluate(f => f.scrollWidth <= f.clientWidth)).toBeTruthy();
});

test('layout mobile sem rolagem horizontal e controles rotulados', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  for (const [caminho, titulo] of [['/registrar', 'Guardar uma experiência'], ['/?q=coxinha&nota_min=0', 'Resultados']]) {
    await page.goto(caminho);
    await expect(page.getByRole('heading', { name: titulo })).toBeVisible();
    const tamanho = await page.evaluate(() => ({ largura: document.documentElement.scrollWidth, janela: innerWidth }));
    expect(tamanho.largura).toBeLessThanOrEqual(tamanho.janela);
    const semRotulo = await page.locator('input:not([type=hidden]), select, textarea').evaluateAll(campos => campos.filter(c => !c.labels?.length).map(c => c.id));
    expect(semRotulo).toEqual([]);
  }
  await page.screenshot({ path: 'test-results/busca-mobile.png', fullPage: true });
  await page.goto('/');
  await page.locator('.nome-item').first().click();
  await expect(page.getByRole('link', { name: 'Editar item' })).toBeVisible();
  await page.screenshot({ path: 'test-results/item-mobile.png', fullPage: true });
  await page.getByRole('link', { name: 'Editar item' }).click();
  await expect(page.getByRole('heading', { name: 'Editar item' })).toBeVisible();
  const tamanho = await page.evaluate(() => ({ largura: document.documentElement.scrollWidth, janela: innerWidth }));
  expect(tamanho.largura).toBeLessThanOrEqual(tamanho.janela);
  const semRotulo = await page.locator('input:not([type=hidden]), select, textarea').evaluateAll(campos => campos.filter(c => !c.labels?.length).map(c => c.id));
  expect(semRotulo).toEqual([]);
  await page.goto('/registrar');
  await page.screenshot({ path: 'test-results/cadastro-mobile.png', fullPage: true });
});

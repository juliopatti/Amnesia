// Gera docs/arquitetura.svg a partir de docs/arquitetura.mmd. Uso: npm run diagrama
const fs = require('fs');
const path = require('path');
const { chromium } = require('@playwright/test');

const RAIZ = path.resolve(__dirname, '..');
const FONTE = path.join(RAIZ, 'docs', 'arquitetura.mmd');
const IMAGEM = path.join(RAIZ, 'docs', 'arquitetura.svg');
const MERMAID = path.join(RAIZ, 'node_modules', 'mermaid', 'dist', 'mermaid.min.js');

// O Mermaid só desenha dentro de um navegador; a página fica em branco, sem rede.
async function desenhar(pagina, codigo) {
  await pagina.addScriptTag({ path: MERMAID });
  return pagina.evaluate(async (fonte) => {
    // Rótulos em texto SVG e fundo branco: a imagem fica legível também no tema escuro.
    mermaid.initialize({ startOnLoad: false, htmlLabels: false, flowchart: { htmlLabels: false } });
    const { svg } = await mermaid.render('arquitetura', fonte);
    const raiz = new DOMParser().parseFromString(svg, 'image/svg+xml').documentElement;
    raiz.style.backgroundColor = '#fff';
    return new XMLSerializer().serializeToString(raiz);
  }, codigo);
}

async function main() {
  const executavel = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  const navegador = await chromium.launch(executavel ? { executablePath: executavel } : {});
  try {
    const svg = await desenhar(await navegador.newPage(), fs.readFileSync(FONTE, 'utf8'));
    fs.writeFileSync(IMAGEM, svg + '\n');
    console.log('Gerado: docs/arquitetura.svg');
  } finally {
    await navegador.close();
  }
}

main().catch((erro) => {
  console.error(erro.message);
  process.exit(1);
});

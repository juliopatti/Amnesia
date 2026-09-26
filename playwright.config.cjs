const { defineConfig, devices } = require('@playwright/test');

// Senha e segredo fictícios, só para o Worker local dos testes (hash com 1000 iterações).
const SENHA_HASH = 'pbkdf2_sha256$1000$YW1uZXNpYS1lMmUtc2FsIQ$piZL9wuN6ZkHFv-5vwfR9W4ASiJKNoIdlxk6f0V3N_k';
const SEGREDO_SESSAO = 'segredo-de-sessao-dos-testes-e2e-0000';

module.exports = defineConfig({
  testDir: './tests/e2e',
  globalSetup: './tests/e2e/entrar.setup.cjs',
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:8790',
    ...devices['Pixel 7'],
    browserName: 'chromium',
    storageState: '.wrangler/test-state/sessao-e2e.json',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {},
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `uv run pywrangler dev --ip 127.0.0.1 --port 8790 --persist-to .wrangler/test-state ` +
      `--var 'SENHA_HASH:${SENHA_HASH}' --var 'SEGREDO_SESSAO:${SEGREDO_SESSAO}'`,
    url: 'http://127.0.0.1:8790/saude',
    reuseExistingServer: false,
    timeout: 120000,
  },
});

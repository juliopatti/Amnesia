# Atalhos para os comandos do README. `make` ou `make ajuda` lista todos.
.DEFAULT_GOAL := ajuda
.PHONY: ajuda instalar testar banco senha rodar navegador banco-e2e e2e diagrama publicar

ajuda: ## Lista os atalhos disponíveis
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

instalar: ## Instala as ferramentas do projeto (uv e npm)
	uv sync --locked
	npm ci

testar: ## Roda os testes offline (só stdlib, sem rede)
	PYTHONPATH=src python3 -m unittest discover -s tests -v

banco: ## Cria ou atualiza o banco local
	uv run pywrangler d1 migrations apply amnesia --local

senha: ## Cria a senha do app local (.dev.vars)
	python3 scripts/senha.py --dev-vars

rodar: ## Liga o app em http://localhost:8787
	uv run pywrangler dev

navegador: ## Baixa o Chromium usado pelos testes e pelo diagrama
	npx playwright install chromium

banco-e2e: ## Prepara o banco isolado dos testes de navegador
	uv run pywrangler d1 migrations apply amnesia --local --persist-to .wrangler/test-state

e2e: banco-e2e ## Roda os testes de navegador
	npm run test:e2e

diagrama: ## Gera docs/arquitetura.svg a partir de docs/arquitetura.mmd
	npm run diagrama

publicar: ## Aplica as migrações e publica na Cloudflare (ambiente producao)
	uv run pywrangler d1 migrations apply amnesia --remote --env producao
	uv run pywrangler deploy --env producao

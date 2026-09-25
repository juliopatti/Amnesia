# amnesia

Registro pessoal de lugares, produtos e experiências. Aplicativo privado, para uma
pessoa; repositório de código público durante a avaliação da disciplina.

As convenções de desenvolvimento, documentação e testes estão em
[Boas práticas](BOAS_PRATICAS.md). Nesta fase, os commits vão direto para `main`.

**Incremento 1:** esquema D1 + FTS5, regras de domínio, adaptador D1 de leitura,
testes offline e uma página inicial que confirma a conexão com o banco local.
Ainda não há formulário, upload, busca na interface ou publicação.

## O que já está decidido

- Item: nome obrigatório, descrição livre opcional e detalhes por categoria.
- Experiência: data, relato livre, pedido/provado, nota, preço, tags e “repetiria?”.
- Notas: **0, 0,5, 1, …, 4,5, 5**. Sem nota é `NULL`, diferente de zero.
- No incremento 2, a interface terá estrelas clicáveis, seleção de meia estrela,
  opção explícita de zero e opção de limpar a avaliação.
- Relato da experiência e descrição do item são textos independentes.
- Preços em centavos de reais. Horários ISO 8601 com offset fixo `-03:00`.
- `categorias` + JSON em `itens.detalhes`: novas categorias não exigem novas tabelas.
  Também será necessário definir seus campos em `CAMPOS_CATEGORIA` e no formulário.
- A FTS tem um documento por item (`rowid = itens.id`) e inclui descrição, nome,
  localização, detalhes, relatos, pedidos e tags.
- O índice ainda está vazio. A escrita dos registros e a sincronização transacional
  da FTS entram juntas no incremento 2; a interface de busca entra no 3.

## Conta Cloudflare

O desenvolvimento local deste incremento não exige login nem credenciais.
Na publicação, será possível usar uma conta existente no
[painel Cloudflare](https://dash.cloudflare.com/), criando recursos próprios para
o amnesia. D1 e R2 usam bindings; não são necessárias integrações com Telegram,
Google Drive, Google Sheets ou provedores de IA.

## Passo a passo: rodar no seu computador (Linux)

Execute os blocos abaixo **um por vez**, no terminal. Se algum comando falhar,
pare nesse passo e copie a mensagem de erro, sem incluir segredos.

### 1. Entre na pasta

Abra a pasta do projeto no seu editor e use a opção de abrir um terminal nessa
pasta. Confirme que `README.md` e `pyproject.toml` aparecem ao executar `ls`.

### 2. Execute os testes offline

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Resultado esperado: a última linha diz `OK`. Este comando não instala pacotes,
não acessa sua conta e não precisa de internet. Usa Python 3.12 ou mais recente.

### 3. Confira Node e uv

```bash
node --version
```

O ambiente validado usa Node 22.23.2. Node é usado pela ferramenta da Cloudflare;
o backend do app continua sendo Python e não há build do frontend.

```bash
uv --version
```

Se aparecer `command not found`, instale o uv pelo instalador oficial:

```bash
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/amnesia-instalar-uv.sh
sh /tmp/amnesia-instalar-uv.sh
```

Feche e abra o terminal, entre novamente na pasta do passo 1 e repita
`uv --version`. O uv gerencia o ambiente Python do projeto; não é uma dependência
do app publicado. [Instalação oficial](https://docs.astral.sh/uv/getting-started/installation/).

### 4. Prepare as ferramentas do projeto

```bash
uv sync --locked
```

Isso instala as ferramentas oficiais `workers-py` (comando `pywrangler`) e
`workers-runtime-sdk`, junto das dependências delas, em `.venv/`.
As versões Python estão registradas em `uv.lock`. Não precisa ativar o ambiente
manualmente: os próximos comandos usam `uv run`. Ao iniciar o Worker, o pywrangler
também pode criar `.venv-workers/` e baixar a versão de Python correspondente ao
runtime da Cloudflare. Isso é automático e não substitui o Python do sistema.

### 5. Crie as tabelas no banco local

```bash
uv run pywrangler d1 migrations apply amnesia --local
```

Se pedir confirmação para aplicar a migração, responda `y` e pressione Enter.
A ferramenta pode baixar o Wrangler no primeiro uso. Resultado esperado:
`0001_inicial.sql` aplicada com sucesso.

**`--local` significa no seu computador.** Os dados ficam em `.wrangler/state/`.
Não precisa criar D1 no painel nem fazer login. O identificador com zeros em
`wrangler.jsonc` é proposital, usado só nesta fase local.
Você pode repetir o comando: migrações já aplicadas não são reaplicadas.

### 6. Ligue o app

```bash
uv run pywrangler dev
```

Espere aparecer `Ready on http://localhost:8787` (ou o endereço informado pela
ferramenta). A primeira execução pode baixar o runtime Python. Deixe esse terminal
aberto e visite <http://localhost:8787> no navegador do computador.

Você deve ver **amnesia.**, a frase “Você já esteve aqui. Óbvio que não lembra.”
e as categorias Lugares e Produtos. A página é apenas a base visual deste incremento.

Abra também <http://localhost:8787/saude>. Deve aparecer um JSON com
`"estado":"ok"`, as duas categorias e contagens zeradas.

Para desligar, volte ao terminal e pressione **Ctrl+C**. Seus dados locais permanecem.

### Se algo der errado

- **“Base indisponível” / resposta 503:** execute o passo 5 na mesma pasta e reinicie
  o comando do passo 6.
- **“uv: command not found”:** reabra o terminal após instalar uv; repita o passo 3.
- **Porta 8787 ocupada:** rode `uv run pywrangler dev --port 8788` e abra a porta 8788.
- **Erro ao baixar pacotes/runtime:** a instalação inicial precisa de internet;
  os testes do passo 2 continuam funcionando offline.

Não execute `deploy` nem substitua o identificador fictício ainda. A publicação
protegida pelo Access será feita no incremento 5. `workers.dev` e previews estão
desabilitados na configuração atual.

## Organização e testes

| Arquivo | Responsabilidade |
| --- | --- |
| `src/dominio.py` | Funções puras, validação, normalização de notas e datas |
| `src/servicos.py` | Caso de uso com armazenamento recebido por argumento |
| `src/armazenamento.py` | Consultas parametrizadas e conversão do binding D1 |
| `src/worker.py` | Rotas `/` e `/saude`; respostas HTTP |
| `src/paginas.py` | HTML com escape de conteúdo dinâmico |
| `migrations/0001_inicial.sql` | Tabelas, índices e FTS5 |
| `tests/` | Domínio, dublês de armazenamento/binding e SQLite em memória |

Os testes cobrem todas as meias estrelas, zero versus ausência, entradas inválidas,
texto livre, data em `-03:00` na virada do dia, SQL parametrizado, chaves estrangeiras,
JSON, média que inclui zero, nova categoria e FTS por palavras, prefixos e acentos.
SQLite em memória ajuda a verificar SQL; não substitui testar o binding no runtime.

A suíte offline também está configurada para rodar a cada push no GitHub, em
Python 3.12 e 3.14. Confira o resultado na aba **Actions → Testes** após enviar
o repositório. A [primeira execução no GitHub](https://github.com/juliopatti/Amnesia/actions/runs/36088361619)
foi aprovada nas duas versões. O workflow não realiza deploy.

Validação realizada neste incremento: 18 testes offline aprovados, migração aplicada
no D1 local, `/` e `/saude` com HTTP 200, caminho inexistente com 404 e POST com 405.
Testado com pywrangler 1.17.4, SDK 1.9.0 e Wrangler 4.139.0. A SDK converte os
resultados D1 para estruturas Python; o adaptador e seu dublê usam esse contrato.
`pylock.toml` registra a SDK empacotada pelo pywrangler para o runtime.

Stdlib usada no runtime: `datetime`, `decimal`, `html` e `urllib.parse`.
Elas estão contempladas na documentação de compatibilidade de Python Workers;
`decimal` usa a implementação C compilada para WebAssembly. Não usamos `zoneinfo`.
`sqlite3`, `pathlib` e `unittest` são usados apenas nos testes locais.
[Referência de compatibilidade](https://developers.cloudflare.com/workers/languages/python/stdlib/).

Não há dependência de aplicação adicional. A SDK e o pywrangler são as ferramentas
oficiais descritas nos [exemplos de Python Workers](https://github.com/cloudflare/python-workers-examples/tree/main/hello).

## Segredos e publicação futura

`.env`, `.dev.vars`, caches e ambientes virtuais estão ignorados pelo Git.
`.env.example` contém apenas orientações; nenhum segredo é necessário nesta etapa.
D1/R2 serão acessados por bindings, não pelas credenciais do seu outro projeto.
Segredos futuros de produção serão cadastrados na Cloudflare, nunca no repositório.

No incremento 5, o roteiro será: autenticar na conta, criar D1 e R2 próprios do
amnesia, aplicar migrações remotas, configurar Access somente para seu e-mail e
publicar/testar as rotas protegidas. Não é necessário modificar o outro projeto.

## Próximos incrementos

2. Cadastro mobile de item e experiência, estrelas de meia em meia, textos livres,
   foto opcional reduzida no navegador e sincronização da FTS.
3. Busca única, categoria e faixa de nota média.
4. Página do item com linha do tempo, média e “voltaria/compraria de novo?”.
5. Deploy, Access e teste de registro em menos de 30 segundos no celular.

Um incremento por vez. Nenhuma integração com IA nesta fase.

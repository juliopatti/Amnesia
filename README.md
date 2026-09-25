# amnesia

Registro pessoal de lugares, produtos e experiências. Aplicativo privado, para uma
pessoa; repositório de código público durante a avaliação da disciplina.

[Boas práticas](BOAS_PRATICAS.md) descreve as convenções de código, documentação e
testes. Nesta fase, os commits vão direto para `main`.

## O que funciona agora — incremento 4

- Registrar itens em sete categorias: **Bares e restaurantes**, **Lugares** (cidades,
  passeios, turismo), **Produtos**, **Filmes**, **Séries**, **Livros** e **Música**.
  Só o nome exige digitação; cada categoria tem seus próprios detalhes (endereço e
  telefone, direção e ano, autoria e editora, artista e álbum…).
- Guardar só o item ou já registrar uma experiência na mesma tela.
- Registrar outras experiências em um item existente.
- Escolher notas de **0 a 5 em passos de meia estrela**, por toque ou teclado.
  “Sem nota” é diferente de zero.
- Escrever a descrição do item e o relato de cada experiência separadamente.
- Informar data, pedido/provado, preço e tags.
- Responder “Voltaria / compraria de novo?” numa escala: Sem sombra de dúvidas,
  Voltaria ué, Talvez, Uai sei não, Não por livre espontânea vontade ou Nem a pau,
  Juvenal! “Sem resposta” é diferente de qualquer uma delas.
- Guardar telefone/WhatsApp de bares, restaurantes e lugares. A página deles oferece
  **Ligar** e **WhatsApp**.
- Anexar até 3 fotos por experiência. O navegador reduz para até 1600 pixels no
  maior lado e 768 KiB por foto, converte para JPEG e remove os metadados.
- Consultar os itens por categoria e registrar outra experiência a partir deles.
- Manter o índice FTS atualizado na mesma transação do cadastro.
- **Buscar** pelo campo no topo de qualquer página: nome, descrição do item, relatos,
  pedidos, tags, endereço, bairro, cidade e detalhes do produto. Um item aparece uma
  vez, mesmo com várias experiências que mencionem o termo; o trecho encontrado fica
  destacado.
- Filtrar por categoria e por faixa de **nota média do item** (0 a 5, meia em meia).
- Cada aba de categoria tem seu botão **+ Registrar**, que já abre o formulário
  naquela categoria.
- **Editar** o item (nome, categoria, descrição e detalhes) e cada experiência
  (nota, relato, data, pedido, preço, tags e “voltaria?”). A busca acompanha.
- **Excluir** um item inteiro, uma experiência ou uma foto, sempre com uma tela de
  confirmação que diz o que vai junto.

Tocar no nome de um item abre a página dele: **nota média** em estrelas, resumo do
“Voltaria?” (quantas respostas foram sim e qual foi a última), descrição, endereço,
contatos e as experiências da mais recente para a mais antiga, com a miniatura da
primeira foto. Cada experiência abre na própria página, com tudo o que foi anotado.
A publicação, com login próprio, é o incremento 5.

## Rodar no seu computador (Linux)

Execute os blocos **um por vez**, no terminal aberto na pasta que contém este
README. Se um comando falhar, pare nesse passo e copie a mensagem de erro sem
segredos. Nenhum destes passos altera sua conta Cloudflare.

### 1. Confira as ferramentas

```bash
python3 --version
node --version
uv --version
```

Python 3.12 ou mais recente serve para os testes offline. O ambiente validado usa
Node 22.23.2. Node executa as ferramentas de desenvolvimento: o backend continua
em Python e o frontend não tem build.

Se aparecer `uv: command not found`, instale pelo instalador oficial:

```bash
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/amnesia-instalar-uv.sh
sh /tmp/amnesia-instalar-uv.sh
```

Reabra o terminal na pasta do projeto e confira `uv --version` novamente.
[Instalação oficial do uv](https://docs.astral.sh/uv/getting-started/installation/).

### 2. Instale as ferramentas do projeto

```bash
uv sync --locked
npm ci
```

O uv cria `.venv/`. O pywrangler pode criar `.venv-workers/` e baixar o Python do
runtime Cloudflare automaticamente. Isso não substitui o Python do sistema.
O npm instala Wrangler e Playwright nas versões do `package-lock.json`.
Não é necessário ativar ambientes virtuais manualmente.

A aplicação usa a SDK oficial de Workers e uma cópia local do **htmx 2.0.8**
([licença](static/htmx.LICENSE)). Playwright é exclusivo dos testes de navegador;
Wrangler é a ferramenta oficial de desenvolvimento. Não há ORM, framework web,
biblioteca de processamento de imagens ou dependência de CDN.

### 3. Execute os testes offline

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Resultado esperado: **83 testes e `OK`**. Esta suíte usa apenas a stdlib,
não faz chamadas de rede e pode rodar mesmo sem as instalações do passo 2.

### 4. Prepare ou atualize o banco local

```bash
uv run pywrangler d1 migrations apply amnesia --local
```

Responda `y` se houver confirmação. O comando aplica só as migrações que faltam.
Rode de novo sempre que atualizar o código: sem a migração nova, o app falha ao
gravar.

A `0004_categorias.sql` move os itens de “Lugar” para “Bares e restaurantes”, que era o
uso até então; “Lugares” passa a ser para cidades e turismo. Os detalhes não mudam.
A `0003_voltaria.sql` converte as respostas antigas: **Sim** vira “Voltaria, ué” e
**Não** vira “Não por livre espontânea vontade”; sem resposta continua sem resposta.
Antes de aplicá-la sobre dados reais, faça uma cópia:

```bash
cp -r .wrangler/state .wrangler/state-copia-$(date +%Y%m%d-%H%M)
```

`--local` guarda o banco em `.wrangler/state/`. O identificador com zeros em
`wrangler.jsonc` é proposital para esta fase. Não precisa criar D1 no painel.
O R2 local também é simulado pela ferramenta, sem conta ou assinatura.

### 5. Ligue o app

```bash
uv run pywrangler dev
```

Espere aparecer `Ready on http://localhost:8787` ou o endereço informado pela
ferramenta. Abra <http://localhost:8787> no navegador do computador e mantenha o
terminal aberto. Pressione **Ctrl+C** quando quiser desligar. Os dados permanecem.

Se a porta estiver ocupada, use `uv run pywrangler dev --port 8788` e abra a porta
8788. Se o app mostrar erro de banco, confira o passo 4 e reinicie o servidor.
A instalação inicial das ferramentas e do runtime precisa de internet.

### 6. Experimente o cadastro, a busca e a edição

1. Clique em **Registrar experiência**.
2. Digite um nome, por exemplo “Bar de teste”.
3. Toque na metade esquerda de uma estrela para meia estrela, ou na direita para
   a estrela inteira. **0 estrelas** e **Sem nota** têm opções próprias.
4. Escreva “Coxinha fria” no campo **Como foi?**.
5. Se quiser, abra **Mais detalhes** ou escolha uma foto.
6. Clique em **Guardar experiência**. Deve aparecer “Pode esquecer. A gente anotou.”
7. Clique em **Outra experiência aqui** para registrar uma segunda visita no mesmo item.

Depois, na página inicial:

1. Digite `coxinha` no campo do topo. O bar aparece uma vez, com “Coxinha”
   destacado no relato — mesmo que o nome do bar não tenha essa palavra.
2. Troque por `COXINHA` ou `coxínha`: maiúsculas e acentos não importam. Plural e
   diminutivo também não: `espetinho` encontra “espeto”, e vice-versa.
3. Escolha **Lugares** ou **Produtos** e uma faixa em **Média de … até …**.
   Com JavaScript, os resultados mudam sem recarregar; sem ele, use **Buscar**.
4. Teste entradas estranhas, como `"NOT (` ou `!!!`: a busca responde com uma
   mensagem, nunca com erro. **Limpar busca** volta à lista completa.

Para corrigir algo:

1. Na lista, toque no **nome** do item. A página mostra o item e as experiências.
2. **Editar item** muda nome, categoria, descrição e detalhes. **Excluir item** apaga o
   item com todas as experiências e fotos, depois de mostrar o que vai junto.
3. Toque numa experiência e use **Editar experiência** ou **Excluir**.
4. Sob cada foto há **Remover foto**. Nada é apagado sem a tela “Excluir de vez”.
5. Busque pelo nome antigo e pelo novo: só o novo deve aparecer.

Se apagar a data ao editar, a original é mantida. Ainda não é possível mover uma
experiência para outro item.

Para cadastrar apenas um item, preencha o nome e use **Só guardar o item, sem
experiência**. A descrição do item fica em **Mais detalhes**. Fotos pertencem às
experiências, por isso exigem o botão **Guardar experiência**.

Se a foto falhar, o texto já estará salvo. A tela oferece **Tentar fotos novamente**
ou um link para continuar com o registro salvo. Também é possível anexar fotos na
página de confirmação posteriormente. Uma foto que o navegador não consiga abrir
(por exemplo, certos arquivos HEIC) deve ser exportada para JPEG, PNG ou WebP.

Sem JavaScript, cadastro, edição, exclusão e seleção de nota continuam funcionando; a redução e o
envio de fotos precisam de JavaScript. Os detalhes das duas categorias ficam
visíveis nesse modo, mas o servidor usa somente os da categoria selecionada.

## Testes de navegador e integração real

Depois dos passos 1 e 2, instale o navegador de testes uma vez:

```bash
npx playwright install chromium
```

Se o Playwright indicar bibliotecas do sistema ausentes, execute
`npx playwright install --with-deps chromium`; essa variante pode pedir sua senha
para instalar pacotes do sistema.

Prepare o banco isolado e execute os testes:

```bash
uv run pywrangler d1 migrations apply amnesia --local --persist-to .wrangler/test-state
npm run test:e2e
```

O Playwright inicia e encerra o Worker na porta **8790**, usando D1 e R2 locais em
`.wrangler/test-state/`. A porta precisa estar livre. Seus registros de desenvolvimento
em `.wrangler/state/` não são usados. Os dados fictícios podem permanecer entre
execuções; os testes geram nomes únicos.

Para usar o Chrome já instalado no Linux, em vez do Chromium baixado:

```bash
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome npm run test:e2e
```

Os 10 cenários verificam cadastro, meia estrela/zero/ausência, teclado, produto,
campos preservados após erro, htmx, cadastro sem JavaScript, escape de HTML, redução
real de imagem, falha e repetição de upload, leitura da foto no R2, proteção de
origem, reenvio concorrente, busca (relato, acentos, filtros, htmx, entradas especiais
e estados vazios), categorias com detalhes próprios e filtro, edição com e sem
JavaScript refletida na busca, exclusão de
experiência e de foto com confirmação, layout mobile sem rolagem horizontal e todas
as categorias visíveis no computador.

Em caso de falha, capturas e traces ficam em `test-results/`, ignorado pelo Git.
Esses arquivos podem conter o conteúdo usado no teste; use somente dados fictícios.

## Integração contínua

A aba [Actions → Testes](https://github.com/juliopatti/Amnesia/actions/workflows/testes.yml)
mostra as execuções de cada push. O workflow configura:

- Suíte offline em Python 3.12 e 3.14.
- Testes de navegador com Chromium, Python Worker, D1 e R2 locais.

Não exige segredos Cloudflare e não realiza deploy. As dependências são baixadas
na preparação do runner; os testes do app usam apenas recursos locais.

Validação local do incremento 4 e das categorias: **83 testes offline e 10 cenários de
navegador aprovados**. O teste automatizado de envio rápido não
substitui cronometrar uma pessoa usando um celular real; essa validação permanece
para a entrega publicada. Também não houve teste em Safari/iPhone nesta etapa.

## Organização e decisões técnicas

| Arquivo | Responsabilidade |
| --- | --- |
| `src/dominio.py` | Validações, normalizações e montagem segura da consulta de busca |
| `src/servicos.py` | Buscar, criar, editar e excluir; dependências injetadas |
| `src/armazenamento.py` | SQL parametrizado, transações D1, projeção e consulta FTS, adaptador R2 |
| `src/worker.py` | Rotas HTTP, limites de corpo e checagem de origem |
| `src/paginas.py` | HTML com escape de valores |
| `static/` | CSS, ícone da seta dos selects, htmx local e JavaScript de formulário/fotos |
| `migrations/` | Evolução do esquema sem reescrever migrações anteriores |
| `tests/` | Regras, serviços com dublês, SQL real em SQLite e testes de navegador |

O item contém nome, descrição e detalhes em JSON por categoria. `CATEGORIAS`, em
`src/dominio.py`, é a fonte única de nomes, ordem e campos: o formulário, os filtros
e a página do item são gerados a partir dela. A tabela `categorias` guarda os mesmos
slugs só para a integridade referencial, e um teste garante que as duas batem. Nova
categoria = entrada em `CATEGORIAS` + migração inserindo o slug; nenhuma tabela muda.

Subcategorias (Música → Rock, Blues…) já são suportadas pelo desenho, embora nenhuma
exista: o slug usa a raiz como prefixo (`musica.rock`), herda os campos dela e
aparece ao filtrar pela raiz. Para criar uma, basta inserir o slug e o nome na tabela.
Nos formulários, cada campo de detalhe leva a categoria no nome (`restaurante-bairro`),
para que categorias com os mesmos campos não gerem ids ou nomes repetidos. Experiências têm data, nota opcional, relato,
pedido, preço em centavos de reais, “voltaria?” de 0 (Nem a pau) a 5 (Sem sombra de
dúvidas) ou nulo, e tags. O telefone fica nos detalhes do lugar. Com DDD, o app
assume +55 para o WhatsApp; sem DDD ou 0800, oferece só a ligação.

As chaves de envio evitam duplicação ao repetir um formulário: **o primeiro envio
confirmado prevalece**. Para registrar outra experiência, abra um novo formulário.
A gravação do item, experiência, tags e documento FTS ocorre em um único
`D1.batch`. Se uma etapa falha, o lote é desfeito. A FTS agrega nome, descrição,
localização, detalhes, relatos, pedidos e tags, com um documento por item.

A busca reduz cada palavra a um radical simples do português, sem diminutivo, plural
e vogal final (`espetinhos` → `espet`), e procura esse radical como prefixo entre
aspas (`"espet"*`), exigindo todas as palavras. Radicais curtos demais não são
cortados, para `caminho` não virar `cam`; em troca, `bolinho` e `bolo` continuam
separados. Não é um stemmer completo nem usa dependência externa. Como
cada palavra fica entre aspas, `*`, parênteses e `AND`/`OR`/`NOT`/`NEAR` viram texto
comum, e a consulta à FTS nunca fica malformada. O tokenizador `unicode61
remove_diacritics 2`, já existente, ignora acentos e maiúsculas; não houve migração.
Texto sem nenhuma letra ou número mostra um aviso em vez de listar tudo. O limite é
200 caracteres e 10 palavras. Os resultados são ordenados por relevância (bm25, com
peso maior para o nome).

A média usa só experiências avaliadas: zero conta, “sem nota” não. Com qualquer
limite de nota, itens sem avaliação ficam fora; sem limite, aparecem. A faixa compara
a média exata, exibida com até duas casas. Filtros inválidos (por exemplo, mínimo
maior que o máximo) retornam 422 com a mensagem na própria página; o htmx foi
configurado para exibir essa resposta. A média é calculada a cada consulta, o que
serve para um caderno pessoal; o desempenho com muitos registros ainda será medido.

Fotos usam uma segunda requisição. R2 e D1 não têm transação conjunta: se a gravação
dos metadados falha, o serviço tenta remover o objeto enviado. Falha simultânea de
D1 e R2 pode deixar objeto órfão; reconciliação automática ainda não está implementada.
Na exclusão, o banco é alterado primeiro, num único lote com a FTS, e só depois o
objeto sai do R2. Se o R2 falhar, a foto já some do app, mas o arquivo privado fica
órfão no bucket e o Worker registra só a quantidade no log. As exclusões removem
fotos, tags e experiência explicitamente, sem depender de `ON DELETE CASCADE`.
A edição substitui os campos e as tags e reindexa o item no mesmo `D1.batch`.

O servidor limita tamanho, quantidade e verifica MIME/assinatura JPEG. Não é uma
validação completa por decodificação de imagem no servidor.

As escritas exigem `Origin` igual ao site e rejeitam requisições marcadas como
cross-site. SQL usa parâmetros, HTML usa escape e respostas incluem CSP e
`nosniff`. Fotos são servidas pelo Worker; nenhum bucket público é necessário.
Isso não substitui autenticação: o login próprio será implementado antes da publicação.

Stdlib usada no runtime: `datetime`, `decimal`, `html`, `json`, `re`, `urllib.parse`
e `uuid`. Compatibilidade conferida na [documentação de Python Workers](https://developers.cloudflare.com/workers/languages/python/stdlib/)
e exercitada no runtime local. Horários usam offset fixo `-03:00`, sem `zoneinfo`.
SQLite e dublês ajudam a testar SQL e falhas, mas não substituem a integração real.

## Segredos e publicação futura

`.env`, `.dev.vars`, bancos locais, fotos locais, ambientes e resultados de testes
estão ignorados pelo Git. `.env.example` tem apenas orientações. Não é necessário
copiar credenciais de outro projeto. Dados reais não devem entrar no repositório público.

### Mudança de plano: publicação sem cartão

O plano original usava R2 para fotos e Cloudflare Access para o login. Os dois exigem
cartão de crédito cadastrado, mesmo no plano gratuito, o que está fora das
restrições do projeto. O incremento 5 passa a usar apenas serviços sem cartão:

| Parte | Antes | Agora |
| --- | --- | --- |
| App e textos | Workers + D1 | Workers + D1 no plano gratuito (sem cartão) |
| Fotos | R2 | Pasta privada no Google Drive do dono, via API do Drive |
| Login | Cloudflare Access | Login próprio com senha, segredo do Worker e cookie seguro |
| Endereço | Domínio próprio | `amnesia.<conta>.workers.dev`, gratuito |

A API do Drive não exige conta de cobrança; o armazenamento sai da assinatura Google
do dono. As fotos continuam atrás de um adaptador (hoje o R2 local), então trocar o
destino não afeta o resto do app. Se o Drive se mostrar inviável, a alternativa é
guardar a foto como BLOB no próprio D1 (limite de 2 MB por registro e 500 MB por
banco no plano gratuito). O login usará apenas a stdlib (`hashlib`, `hmac`,
`secrets`), com compatibilidade conferida no runtime antes do uso.

## Próximos incrementos

5. Login próprio, fotos no Google Drive, publicação em `workers.dev` e teste de
   registro em menos de 30 segundos no celular.

Um incremento por vez. Nenhuma integração com IA nesta fase.

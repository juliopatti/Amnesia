# Prompt inicial (CO-STAR)

Prompt usado para iniciar o projeto com o Claude Opus 5.5, no formato CO-STAR
(Contexto, Objetivo, Estilo, Tom, Audiência, Resposta). Está preservado como foi
escrito; o que mudou depois está no fim deste arquivo.

---

## C — Contexto
Projeto pessoal: **amnesia — registro de experiências**. Um app "antissocial" pra
quem tem memória de peixe: registro onde fui, o que comi/comprei, se foi bom ou
ruim, e depois acho tudo pela busca. Não é rede social. Não tem outros usuários,
nada é público, não existe compartilhamento. Usuário único: eu.

Avaliações minhas hoje estão espalhadas (Google Maps, iFood, Filmow, MyAnimeList…).
A ideia é concentrar num lugar só, e as opiniões ficam só pra mim.

**Escopo v1:** duas categorias, **lugares** (bares/restaurantes) e **produtos**.
Depois vêm música, filme, série e viagem. Então uma categoria nova não pode exigir
reescrever o esquema.

**Modelo de domínio:**
- **item**: a coisa avaliada (um lugar, um produto). Tem página própria.
  Campos comuns + campos específicos por categoria (lugar: endereço/bairro/cidade;
  produto: marca/onde comprei).
- **experiência**: um encontro datado com o item: nota, texto livre, o que pedi
  ou provei, preço pago, "voltaria/compraria de novo?", fotos, tags.
  Um item tem várias experiências. A página do item é a linha do tempo delas.

**Stack (já decidida, não trocar sem me explicar antes):**
- Cloudflare Workers **Python** (Pyodide). Já uso em outro projeto. Pegadinhas
  conhecidas: sem `zoneinfo` (usar offset fixo -03:00), e qualquer pacote fora da
  stdlib precisa ser confirmado como compatível com Python Workers antes de adotar.
- **D1** (SQLite) como banco, com **FTS5** para a busca.
- **R2** para fotos (reduzir a imagem no navegador antes do upload).
- **Cloudflare Access** na frente de tudo (login por e-mail). Sem sistema de login próprio.
- Frontend: HTML renderizado no servidor + **htmx** + CSS pequeno. Sem React,
  sem build step, sem ORM.
- Custo fixo de infraestrutura: **R$ 0**.

**Fase 2 (NÃO fazer agora, mas deixar o caminho aberto):** um bot de Telegram
com `gpt-5.6-luna` onde mando foto/texto/áudio e ele registra a experiência.
Vou trazer do meu outro projeto a camada de modelo e o webhook. Por isso a lógica
de negócio (criar item, registrar experiência, buscar) deve ser **funções Python
puras, separadas das rotas HTTP**. Elas vão virar as tools do agente depois.

## O — Objetivo
Entregar um esqueleto funcional e usável, não o produto completo. Ordem:
1. Propor o **esquema D1** (tabelas + tabela FTS5 + como encaixa categoria nova)
   e **me mostrar antes de escrever código**.
2. Criar item e registrar experiência (com foto).
3. **Busca única** no topo, que acha por nome, texto, prato, tag, bairro e cidade,
   com filtros por categoria e nota.
4. Página do item: linha do tempo das experiências, nota média, "voltaria?".
5. Deploy + Access configurado.

Critério de sucesso: no celular, registrar uma experiência em menos de 30 s, e
achar "aquele bar da coxinha ruim" digitando "coxinha".

Fora do escopo v1: social, seguidores, feed, recomendação, APIs pagas (inclusive
Google Places), IA, multiusuário, app nativo.

## S — Estilo
- Código simples, poucos arquivos, sem overengineering. Explique antes de
  introduzir qualquer dependência nova.
- Comentários e nomes de domínio em português.
- Testes offline com dublês para a lógica Python (sem rede).
- Segredos fora do código e do Git (`.env` + `.env.example`).
- Mobile-first. Interface limpa, bonita sem ser rebuscada.

## T — Tom
- **Na interface:** bem-humorado e autodepreciativo sobre memória ruim, mas só nos
  microtextos (estados vazios, confirmações, placeholders). Nunca atrapalhando o uso.
  Exemplos: "Você já esteve aqui. Óbvio que não lembra." / "Nenhum registro.
  Ou você nunca foi, ou esqueceu de anotar também."
- **Comigo:** direto e curto. Conclusão e próximo passo, sem leque de opções.
  Se tiver uma recomendação, recomende.

## A — Audiência
- Usuário do app: eu, sozinho, quase sempre no celular, em PT-BR.
- Como dev: sei Python, tenho pouca experiência com frontend. Explique o que for
  de HTML/CSS/htmx quando não for óbvio.

## R — Resposta
Na primeira resposta, **sem código ainda**:
1. Esquema SQL proposto (D1 + FTS5).
2. Estrutura de arquivos.
3. Lista do que EU preciso fazer manualmente (criar D1, bucket R2, Access,
   wrangler), em passos numerados.
4. Plano de incrementos, cada um testável sozinho.

---

## O que mudou depois

- **Fotos:** R2 exige cartão cadastrado, mesmo no plano gratuito. As fotos foram para
  uma pasta privada do Google Drive do dono; o R2 ficou só como simulação local.
- **Login:** Cloudflare Access também exige cartão. Ele deu lugar a um login próprio com
  senha, uma decisão tomada por simplicidade.
- **Endereço:** `workers.dev`, gratuito.
- **Categorias:** de duas para sete (bares e restaurantes, lugares, produtos, filmes,
  séries, livros e música), com subcategorias previstas pelo slug.
- **"Voltaria?":** de sim/não para uma escala de seis respostas.
- **Além do previsto:** edição e exclusão de itens, experiências e fotos, e
  telefone/WhatsApp.
- **Fase 2 (bot com IA):** continua fora. A lógica segue separada das rotas, o que
  mantém o caminho aberto. A v3 prevista é outra: permitir que outra pessoa publique o
  próprio amnesia.

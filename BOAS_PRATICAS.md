# Boas práticas do amnesia

## Fluxo de desenvolvimento

- Repositório público durante a avaliação; dados do aplicativo continuam privados.
- Desenvolvimento direto na `main` nesta fase, com commits pequenos e coerentes.
  Pull requests serão adotados quando o tamanho do projeto justificar.
- Usar a identidade Git do proprietário nos commits, sem trailers de coautoria
  nem assinaturas automáticas de ferramentas.
- Não exigir issues, diário de tarefas, histórico de prompts ou registro de
  contribuições de ferramentas. A documentação descreve o sistema e como validá-lo.
- Antes de um commit, revisar o diff e os arquivos incluídos, executar os testes
  pertinentes e atualizar a documentação afetada.
- Corrigir falhas do CI antes de continuar com novas funcionalidades. O CI atual
  informa o resultado; ele não configura bloqueio de pushes na `main`.

## Código e arquitetura

- Manter a stack aprovada e explicar novas dependências antes de adicioná-las.
- Nomes do domínio e comentários em português; comentários explicam decisões
  que não sejam evidentes pelo código.
- Regras puras separadas de HTTP e persistência. Serviços recebem armazenamento
  e relógio por argumento para permitir testes determinísticos.
- Confirmar compatibilidade de módulos da stdlib com Python Workers e testar a
  integração real quando ela mudar. Usar offset fixo `-03:00`, sem `zoneinfo`.
- Validar entradas no servidor, parametrizar SQL e escapar dados inseridos no HTML.
- Preservar distinções do domínio: nota zero versus ausência, resposta “não” versus
  não informada, preço zero versus desconhecido.
- Alterações futuras de um esquema já publicado usam novas migrações. Não reescrever
  migrações aplicadas em produção. Manter dados e FTS sincronizados atomicamente.
- Evitar abstrações e dependências sem necessidade concreta.

## Estratégia de testes

Escolher os testes pelo comportamento e pelo risco da alteração. Priorizar casos
reais, limites, falhas e regressões; não duplicar a implementação nos testes.
Um bug corrigido deve ganhar um teste de regressão quando for reproduzível.

| Camada | Verificação | Situação |
| --- | --- | --- |
| Unidade | Notas, valores ausentes, datas, textos, categorias e entradas inválidas | Automatizada offline |
| Serviços | Casos de uso com dublês sem rede e dependências injetadas | Base automatizada; ampliar com os cadastros |
| Banco | Restrições, relacionamentos, migrações e FTS em SQLite em memória | Esquema inicial automatizado |
| Runtime | Migração D1 local, binding real e respostas HTTP no Python Worker | Verificação local realizada; ainda fora do CI |
| Integração de escrita | Atomicidade, atualização da FTS, repetição de envio e falhas de upload | Implementar junto do cadastro e fotos |
| Interface e ponta a ponta | Cadastrar, buscar e abrir a linha do tempo pelo navegador | Implementar junto das respectivas telas |
| Acessibilidade | Rótulos, teclado, foco, contraste, mensagens de erro e seleção das estrelas | Verificar ao implementar os formulários |
| Segurança | Escape de HTML, SQL parametrizado, proteção de escritas, uploads e rotas privadas | SQL/escape iniciais testados; ampliar com rotas e Access |
| Desempenho e usabilidade | Registro no celular em menos de 30 s, imagens reduzidas e busca com volume representativo | Medir quando os fluxos estiverem completos |
| Publicação e recuperação | Login permitido/negado, fotos protegidas e recuperação dos dados | Validar antes da entrega publicada |

SQLite local e dublês não comprovam compatibilidade com o runtime Cloudflare.
Um resultado aprovado em uma camada não substitui os testes das demais.

Para executar a suíte offline, na raiz do projeto:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

O workflow `.github/workflows/testes.yml` executa essa suíte em Python 3.12 e 3.14
a cada push. Os testes não fazem chamadas de rede; a preparação do runner baixa
as ferramentas necessárias. Não precisa de segredos nem de conta Cloudflare.
O workflow não faz deploy.

Após enviar o código ao GitHub, abra a aba **Actions**, selecione **Testes** e confira
os dois resultados. Em caso de falha, abra o job e o passo de execução dos testes
para ver qual caso falhou. A execução hospedada só será confirmada após esse envio.

## Documentação e dados

- README com instalação reproduzível, comandos, resultados esperados e limitações.
- Registrar decisões técnicas relevantes e consequências perto do código ou no
  README; criar documentos separados apenas quando necessário para compreensão.
- Manter exemplos e dados de teste fictícios, sem fotos, avaliações ou dados pessoais
  reais no repositório público.
- Segredos ficam em `.env` local ou na configuração da Cloudflare. Versionar apenas
  exemplos sem valores secretos. Revisar o conteúdo antes de publicar.
- Não confundir código público com aplicativo público: páginas e fotos do app
  permanecem protegidas pelo Access, com bucket privado.
- Informar o que foi efetivamente testado e o que ainda depende de validação;
  não tratar uma verificação planejada como concluída.

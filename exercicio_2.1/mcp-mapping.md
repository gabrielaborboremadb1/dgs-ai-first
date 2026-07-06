# Mapeamento de Necessidades → MCP Servers

## Necessidades do projeto

| #   | Necessidade                                          | Operação     | Server escolhido           | Justificativa                                                                                 |
| --- | ---------------------------------------------------- | ------------ | -------------------------- | --------------------------------------------------------------------------------------------- |
| 1   | Ler e escrever código, specs e skills do repositório | Read + Write | `filesystem` (escopo `rw`) | Agentes precisam criar e editar arquivos em `src/`, `specs/`, `skills/`, `prompts/`, `tests/` |
| 2   | Ler documentação de negócio da NovaTech              | Read-only    | `filesystem` (escopo `ro`) | Docs em `docs/novatech/` são fonte de verdade — agentes consultam, nunca editam               |
| 3   | Ler corpus de chunks para recuperação (RAG local)    | Read-only    | `filesystem` (escopo `ro`) | `data/retrieval-corpus/` simula o Azure AI Search localmente; agentes apenas recuperam chunks |
| 4   | Histórico, diffs e branches do repositório           | Read         | `git`                      | Expõe `git log`, `git diff`, `git blame`, `git status` sem acesso a remoto nem credenciais    |
| 5   | Memória persistente de decisões e linguagem ubíqua   | Read + Write | `memory`                   | Grafo local de entidades: termos do domínio, decisões arquiteturais, contexto entre sessões   |
| 6   | Explorar primitivas MCP (tools/resources/prompts)    | Read         | `everything`               | Server educacional; permite testar sampling, listagem de tools e recursos durante aprendizado |

---

## Detalhamento por server

### `filesystem` — instância `repo` (leitura e escrita)

**Pastas:** `./src`, `./specs`, `./skills`, `./prompts`, `./tests`

**O que expõe:**

- **Tools:** `read_file`, `write_file`, `create_directory`, `list_directory`, `move_file`, `search_files`
- **Resources:** arquivos como URIs (`file://`)

**Quem consome:** Dev (geração de código, tasks), Tech Lead (specs, planos), QA (fixtures, testes)

**Por que é o mínimo suficiente:** Exclui `docs/novatech/` e `data/retrieval-corpus/` (tratados como read-only em instância separada), `infra/` (Bicep é gerado manualmente, não por agente em loop), `.github/` (workflows não são modificados por agentes), e arquivos de configuração raiz (`package.json`, `tsconfig.json`, `vitest.config.ts`) que só mudam por decisão humana explícita.

---

### `filesystem` — instância `docs` (somente leitura)

**Pastas:** `./docs/novatech`, `./data/retrieval-corpus`

**O que expõe:**

- **Tools:** `read_file`, `list_directory`, `search_files` (subset read-only — o server não distingue por si só, mas o escopo de pastas garante que não há nada gravável aqui)
- **Resources:** documentos de negócio e chunks como URIs

**Quem consome:** Dev (consulta durante geração do `prompt-builder.ts`), QA (fixtures de teste baseadas em chunks reais), Product Specialist (validação de respostas do assistente)

**Por que é read-only e mínimo suficiente:** `docs/novatech/` é a base documental da NovaTech — qualquer escrita acidental corromperia a fonte de verdade do RAG. `data/retrieval-corpus/` simula o índice de busca; sobrescrever chunks quebraria os testes. Separar em instância própria evita que uma skill mal configurada aponte para o servidor "errado" e escreva onde não deveria. As pastas `docs/adr/`, `docs/runbooks/` e `docs/onboarding.md` ficam **fora** deste escopo porque são artefatos do time (editáveis via instância `repo`) — misturá-las com docs da NovaTech criaria ambiguidade de responsabilidade.

---

### `git`

**Repositório:** `.` (raiz do `novatech-assistant`)

**O que expõe:**

- **Tools:** `git_log`, `git_diff`, `git_status`, `git_show`, `git_blame`, `git_branch`
- Não expõe `push`, `fetch` nem operações de reescrita de histórico

**Quem consome:** Tech Lead (revisar diffs antes de aprovar specs), Dev (contexto de mudanças recentes ao gerar código), QA (rastrear quando um arquivo de fixture mudou)

**Por que é o mínimo suficiente:** O repositório é local — não há remoto configurado nesta fase. O server `git` opera em modo read sobre o histórico; não há como o agente fazer `git push` ou `git reset --hard` por este canal. Limitar ao repositório local (`.`) evita que o server acesse repositórios fora do projeto se o agente construir um path relativo inesperado.

---

### `memory`

**Armazenamento:** grafo local (gerenciado pelo server, sem arquivo explícito no repo)

**O que expõe:**

- **Tools:** `create_entities`, `create_relations`, `add_observations`, `search_nodes`, `open_nodes`, `read_graph`, `delete_entities`, `delete_observations`, `delete_relations`

**Quem consome:** Todos os papéis — especialmente o Tech Lead (registrar decisões arquiteturais entre sessões) e o Dev (linguagem ubíqua do domínio: o que é um "chunk", um "atendente", um "chamado")

**Casos de uso concretos:**

- Entidade `Chunk` → relação `tem_tamanho` → `~1.500 tokens` (ADR-0002)
- Entidade `DocumentoContraditório` → relação `resolução` → `priorizar_vigência` (ADR-0003)
- Entidade `ContextBudget` → observações: `system_prompt=4K`, `chunks=8K`, `histórico=3_turnos`

**Por que é necessário além do git:** O `git` guarda o histórico de arquivos — não rastreia decisões que ainda não viraram commit, nem a semântica de termos do domínio. O `memory` permite que uma sessão do Claude Code "lembre" que `frete_especial` se refere ao PROC-042 sem precisar re-ler ADRs a cada prompt.

---

### `everything`

**O que expõe:**

- **Tools:** `echo`, `add`, `longRunningOperation`, `sampleLLM`, `getTinyImage`
- **Resources:** `tiny-image`, `test-resource`
- **Prompts:** `simple_prompt`, `complex_prompt`

**Quem consome:** Dev e Tech Lead durante aprendizado de MCP

**Por que está no projeto:** Permite testar o fluxo MCP completo (tool call → response, resource subscription, prompt template) sem depender de um server real. É removível em produção — não carrega dados sensíveis nem afeta o código gerado.

---

## Diagrama de escopos (Least Privilege)

```
novatech-assistant/
├── src/          ← filesystem:repo  (rw)
├── specs/        ← filesystem:repo  (rw)
├── skills/       ← filesystem:repo  (rw)
├── prompts/      ← filesystem:repo  (rw)
├── tests/        ← filesystem:repo  (rw)
│
├── docs/
│   ├── novatech/ ← filesystem:docs  (ro)  ← fonte de verdade RAG
│   ├── adr/      ← filesystem:repo  (rw)  ← artefato do time
│   └── runbooks/ ← filesystem:repo  (rw)  ← artefato do time
│
├── data/
│   └── retrieval-corpus/ ← filesystem:docs (ro) ← simula índice de busca
│
├── infra/        ← fora do escopo MCP (Bicep editado manualmente)
├── .github/      ← fora do escopo MCP (pipelines CI/CD não são gerados por agente)
└── .git/         ← git server (read-only sobre histórico)
```

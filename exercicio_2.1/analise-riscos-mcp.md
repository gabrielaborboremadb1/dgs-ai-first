  # Análise de Riscos — MCP Servers Locais (Exercício 2.1, item 4)

## Contexto

Este documento identifica riscos de segurança do uso de MCP servers **neste contexto local** (sem serviços pagos ou externos) e propõe mitigações acionáveis, com base no que foi efetivamente configurado e executado em [mcp.json](mcp.json) e mapeado em [mcp-mapping.md](mcp-mapping.md).

## Evidência de execução

Servers subidos e testados com o agente (Claude Code) conectado via `.mcp/mcp.json` do repositório `novatech-assistant`:

| Evidência | O que comprova |
| --- | --- |
| [evidencia_tools_habilitadas.png](evidencia_tools_habilitadas.png) | Os 5 servers (`novatech-repo`, `novatech-docs`, `novatech-git`, `novatech-memory`, `novatech-everything`) conectados e suas tools listadas no agente. |
| [uso_mcp/1_listar_e_ler_documentos.png](uso_mcp/1_listar_e_ler_documentos.png) | Agente lista e lê um documento de `docs/novatech/` via `novatech-docs` (read-only). |
| [uso_mcp/2_recuperar_chunk_relevante.png](uso_mcp/2_recuperar_chunk_relevante.png) | Agente recupera um chunk relevante de `data/retrieval-corpus/` para uma pergunta do domínio, via `novatech-docs`. |
| [uso_mcp/3_ler_historico_git.png](uso_mcp/3_ler_historico_git.png) | Agente lê o histórico do repositório (`git_log`/`git_status`) via `novatech-git`, sem acesso a `push`/`fetch`. |

Essas evidências mostram o comportamento **esperado** dos servers dentro dos escopos definidos. Os riscos abaixo tratam do que acontece quando esse escopo é violado, mal configurado, ou explorado — cenários que não aparecem nas capturas acima porque a configuração atual já os mitiga parcialmente.

---

## Riscos identificados e mitigações

### Risco 1 — Escopo de `filesystem` amplo demais expõe segredos e arquivos fora do domínio do agente

**Descrição:** O server `@modelcontextprotocol/server-filesystem` concede acesso a qualquer arquivo dentro das pastas informadas em `args`, sem diferenciar tipo de conteúdo. Se alguém apontar o server para a raiz do repositório (`.`) em vez das pastas específicas (`./src`, `./specs`, etc.), ou se um `.env` local (usado para credenciais Azure OpenAI/AI Search em desenvolvimento) acabar dentro de uma pasta escopada, o agente passa a poder ler — e um LLM pode inadvertidamente ecoar em uma resposta, log ou commit — segredos como connection strings e API keys.

**Por que é relevante neste setup:** O `.gitignore` do `novatech-assistant` já exclui `.env` do controle de versão, mas o MCP `filesystem` **não respeita `.gitignore`** — ele expõe qualquer arquivo dentro do caminho configurado, versionado ou não. Um `.env` colocado por engano em `./src` (pasta com escopo `rw`) seria totalmente legível e editável pelo agente.

**Mitigação:**
- Manter os segredos **fora de qualquer pasta listada no `mcp.json`** (ex.: usar `.env` na raiz do projeto, que nunca é passado como argumento a nenhuma instância do `filesystem`).
- Adicionar uma checagem manual (ou hook de pre-commit) que falha se `.env`, `*.pem`, `*.key` ou similares aparecerem dentro de `./src`, `./specs`, `./skills`, `./prompts`, `./tests`, `./docs/novatech` ou `./data/retrieval-corpus`.
- Revisar periodicamente os `args` de cada instância do `filesystem` no `mcp.json` (item já coberto na política de aprovação de servers do Tech Lead) — nenhuma pasta deve ser adicionada sem justificativa explícita de necessidade (least privilege).
- Nunca usar `.` (raiz do repo) ou caminhos absolutos amplos como argumento do `server-filesystem`.

---

### Risco 2 — Escrita habilitada (`novatech-repo`) permite alteração de arquivos sem revisão humana

**Descrição:** A instância `novatech-repo` do `filesystem` expõe `write_file`, `move_file` e `create_directory` sobre `./src`, `./specs`, `./skills`, `./prompts`, `./tests`, `./docs/adr` e `./docs/runbooks`. Isso significa que qualquer ação do agente — inclusive uma alucinação, uma instrução mal interpretada, ou um prompt injection vindo de um documento lido via `novatech-docs` — pode resultar em escrita direta nesses arquivos, sem que nenhum humano tenha validado a mudança antes de ela existir em disco.

**Por que é relevante neste setup:** Diferente de um fluxo de PR remoto (com CI e code review obrigatório), aqui o repositório é **local** — não há gate automático entre "o agente escreveu" e "o arquivo está no working tree". O próprio cenário define que "abrir PR" nesta fase é simulado (arquivo markdown em `docs/pull-requests/`), o que reforça que a única barreira real hoje é a disciplina de revisão humana antes de commitar.

**Mitigação:**
- Tratar toda escrita do agente como **rascunho não commitado**: revisar `git diff`/`git status` antes de `git add`/`git commit` — nunca commitar automaticamente em nome do agente.
- Manter a separação já aplicada no `mcp.json`: fontes de verdade (`docs/novatech/`, `data/retrieval-corpus/`) ficam na instância **read-only** (`novatech-docs`), isolada da instância com escrita (`novatech-repo`), para que um prompt malicioso lido de um documento não consiga se propagar para escrita no mesmo canal.
- Reforçar no `AGENTS.md` (seção Project Management Rules, Gate 3 — Code → Merge) que nenhuma alteração gerada por agente é considerada válida até revisão humana e aprovação registrada, independentemente de já estar em disco.
- Evitar rodar o agente em modo "auto-approve" de tool calls de escrita em sessões sem supervisão.

---

### Risco 3 — Supply chain: servers baixados sob demanda via `npx -y` / `uvx` sem pin de versão

**Descrição:** Todas as entradas do `mcp.json` usam `npx -y @modelcontextprotocol/server-*` ou `uvx mcp-server-git`, que resolvem e baixam a versão mais recente do pacote a cada execução (ou usam cache local sem verificação explícita de versão/hash). Um pacote comprometido no registry (npm ou PyPI) — via typosquatting ou takeover de uma versão — passaria a rodar localmente com os mesmos privilégios de arquivo e processo do usuário, incluindo tudo que o `filesystem`/`git` server tem acesso.

**Por que é relevante neste setup:** Como não há nenhum serviço pago/gerenciado envolvido (é justamente o requisito do exercício), a confiança recai inteiramente sobre pacotes npm/PyPI de terceiros baixados dinamicamente na máquina do desenvolvedor.

**Mitigação:**
- Fixar versões exatas nos `args` (ex.: `@modelcontextprotocol/server-filesystem@2025.x.x`) em vez de deixar `npx -y` resolver `latest`.
- Preferir instalação prévia e auditada (`npm install --save-dev`) com o pacote registrado em `package-lock.json`, em vez de execução ad-hoc via `npx -y` a cada sessão.
- Rodar os servers com o usuário/processo com menor privilégio possível no SO (evitar rodar o editor/agente como administrador).

---

### Risco 4 — `git` server pode expor segredos históricos via `git_show`/`git_blame`

**Descrição:** O server `novatech-git` não permite `push`/`fetch`, mas permite leitura irrestrita do histórico local (`git_log`, `git_show`, `git_blame`). Se em algum commit anterior um segredo tiver sido commitado por engano (cenário comum mesmo com `.gitignore` correto hoje — ele não protege o passado), o agente consegue recuperá-lo lendo o histórico, mesmo que o arquivo já tenha sido removido do estado atual.

**Mitigação:**
- Rodar uma varredura de segredos no histórico (ex.: `gitleaks`/`trufflehog`) antes de conectar o `git` server ao agente, especialmente em repositórios que migraram de outro lugar.
- Caso um segredo já tenha sido commitado, tratá-lo como comprometido (rotacionar a credencial) — remover do histórico não é suficiente e não impede leitura via `git_show` até reescrita de histórico, que é uma operação sensível e fora do escopo deste server (propositalmente).

---

## Resumo — matriz de risco

| # | Risco | Probabilidade | Impacto | Mitigação principal | Enforcement |
| --- | --- | --- | --- | --- | --- |
| 1 | Escopo `filesystem` expõe `.env`/segredos | Média | Alto | Segredos nunca dentro de pastas escopadas no `mcp.json` | Processo + revisão de config |
| 2 | Escrita sem revisão humana (`novatech-repo`) | Alta | Médio | Nenhum commit automático; revisão de diff obrigatória | Processo (Gate 3 do AGENTS.md) |
| 3 | Supply chain via `npx -y`/`uvx` sem pin | Baixa | Alto | Fixar versões, evitar `latest` dinâmico | Config (`mcp.json`) |
| 4 | Segredos históricos via `git_show`/`git_blame` | Baixa | Alto | Varredura de histórico + rotação de credencial comprometida | Processo pontual |

**Observação geral:** nenhum dos riscos acima é mitigável só por prompt/instrução ao agente — todos exigem controle estrutural (escopo de pasta, versionamento de pacote, revisão humana antes de commit), reforçando o princípio de que segurança de MCP é uma questão de configuração e processo, não de "pedir para o agente ter cuidado".

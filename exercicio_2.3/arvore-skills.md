# Árvore de Skills — NovaTech Assistant

> Definida a partir da hierarquia Foundation → Domain → Artifact (ver **Anexo C**) e da lista de artefatos recorrentes do projeto: (1) endpoints Azure Functions com padrão RAG, (2) testes de integração, (3) componentes React (cards + formulários de feedback), (4) documentação técnica (ADRs, READMEs), (5) specs de produto (SDD).
>
> O scaffold do Anexo C já traz 9 arquivos vazios (3 Foundation + 4 Domain + 3 Artifact). Ao mapear esses 9 contra os 5 tipos de artefato recorrente, dois tipos ficam descobertos: **documentação técnica** e **specs de produto** — nenhuma skill do scaffold original os cobre. A árvore abaixo mantém os 9 arquivos originais e adiciona o mínimo necessário para fechar essa lacuna (2 Foundation, 2 Domain, 6 Artifact), sem criar skills que ninguém usaria.

---

## Visão geral

```
skills/
├── foundation/
│   ├── typescript-conventions.md      [existente]
│   ├── error-handling.md              [existente]
│   ├── project-structure.md           [existente]
│   ├── logging-observability.md       [novo]
│   └── env-config.md                  [novo]
│
├── domain/
│   ├── azure-functions-endpoint.md        [existente]
│   ├── azure-ai-search-integration.md     [existente]
│   ├── react-components.md                [existente]
│   ├── testing-patterns.md                [existente]
│   ├── technical-documentation.md         [novo]
│   └── sdd-spec-structure.md              [novo]
│
└── artifact/
    ├── create-rag-endpoint.md          [existente]
    ├── create-integration-test.md      [existente]
    ├── create-react-card.md            [existente]
    ├── create-feedback-form.md         [novo]
    ├── create-adr.md                   [novo]
    ├── create-module-readme.md         [novo]
    ├── create-requirements-spec.md     [novo]
    ├── create-plan-spec.md             [novo]
    └── create-tasks-spec.md            [novo]
```

Regra de leitura (reforçada em cada skill de nível superior): uma skill Domain sempre referencia as Foundation aplicáveis; uma skill Artifact sempre referencia a(s) Domain e Foundation aplicáveis antes de gerar código. Isso evita que um agente gere um artefato "correto isoladamente" mas inconsistente com as convenções do projeto.

---

## Foundation — convenções globais

| Skill                            | Descrição (frase-ativação)                                                                                 | Quem cria                                                    | Quem consome                                                               | Frequência                                                                                                           |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `typescript-conventions`         | "Todo arquivo `.ts`/`.tsx` do repositório (strict mode, imports, naming, no `any`)."                       | Tech Lead (deriva das ADRs; mantido no Ex. 2.3 do Tech Lead) | Todos os Devs + Copilot + Claude Code, em **toda** geração de código TS    | Muito alta — lida antes de qualquer geração de código, em praticamente todo PR                                       |
| `error-handling`                 | "Sempre que um módulo precisar lançar, propagar ou logar um erro."                                         | Tech Lead                                                    | Devs + Copilot/Claude Code (backend, pipeline, bot)                        | Alta — todo endpoint, serviço ou função do pipeline trata erro                                                       |
| `project-structure`              | "Ao criar um novo arquivo/pasta — onde ele deve morar no repositório."                                     | Tech Lead                                                    | Devs + Copilot/Claude Code; também Tech Lead ao revisar PRs fora do padrão | Média — consultada a cada novo módulo/arquivo, não a cada edição                                                     |
| `logging-observability` _(novo)_ | "Sempre que um serviço, endpoint ou função precisar emitir log."                                           | Tech Lead                                                    | Devs + Copilot/Claude Code (todo backend)                                  | Alta — pino é obrigatório (`console.log` proibido pelas ADRs); sem esta skill, Copilot gera `console.log` por padrão |
| `env-config` _(novo)_            | "Ao ler/validar variável de ambiente ou configurar acesso a um serviço Azure (OpenAI, AI Search, Cosmos)." | Tech Lead                                                    | Devs + Copilot/Claude Code (config, infra, CI)                             | Média — poucos pontos de configuração, mas erro aqui vaza segredo ou quebra ambiente inteiro                         |

**Por que adicionar `logging-observability` e `env-config`:** o próprio enunciado da tarefa cita "logging" e "env config" como exemplos de convenção Foundation, e o plan.md do query endpoint já assume pino e variáveis de ambiente Azure como padrão — sem uma skill dedicada, cada Domain/Artifact skill teria que reexplicar a mesma regra, violando o princípio de a Foundation ser a fonte única.

---

## Domain — padrões por camada

| Skill                              | Descrição (frase-ativação)                                                                            | Quem cria                                                                                      | Quem consome                                                       | Frequência                                                                                             |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| `azure-functions-endpoint`         | "Ao estruturar qualquer Azure Function HTTP trigger (query, feedback, health, ou futuros endpoints)." | Tech Lead (com validação do Dev sênior)                                                        | Devs + Copilot/Claude Code                                         | Alta — todo novo endpoint (5+ ao longo do projeto: query, feedback, health, e evoluções)               |
| `azure-ai-search-integration`      | "Ao integrar com Azure AI Search (indexação ou busca de chunks)."                                     | Tech Lead + Dev sênior (conhecimento do protótipo RAG da fase 1)                               | Devs (pipeline de ingestão e query endpoint) + Copilot/Claude Code | Média — usada pelos módulos que tocam busca/indexação (pipeline-ingestao, query-endpoint)              |
| `react-components`                 | "Ao criar qualquer componente do painel web."                                                         | Dev sênior (ou Dev responsável pelo painel)                                                    | Devs do painel web + Copilot/Claude Code                           | Média — concentrada no período de desenvolvimento do painel-web                                        |
| `testing-patterns`                 | "Ao escrever qualquer teste (unitário ou integração) no projeto."                                     | QA (Testing Standards, Ex. 2.1) + Tech Lead (padrão técnico Vitest/msw)                        | Devs + QA + Copilot/Claude Code                                    | Muito alta — todo PR precisa de teste; é a skill mais consultada depois de `typescript-conventions`    |
| `technical-documentation` _(novo)_ | "Ao registrar uma decisão técnica (ADR) ou documentar um módulo (README)."                            | Tech Lead                                                                                      | Devs + Tech Lead + Claude Code                                     | Baixa/Média — ADR só a cada decisão relevante; README a cada módulo novo (5 módulos)                   |
| `sdd-spec-structure` _(novo)_      | "Ao criar ou editar `requirements.md`, `plan.md` ou `tasks.md` de qualquer módulo em `/specs/`."      | Tech Lead (formaliza o fluxo SDD definido na governança de specs, Ex. 2.2 do Delivery Manager) | Product Specialist, Tech Lead, Devs + Claude (chat)/Claude Code    | Alta — cada um dos 5 módulos passa pelos 3 artefatos; mais consultada nas primeiras semanas do projeto |

**Por que adicionar `technical-documentation` e `sdd-spec-structure`:** sem elas, as skills Artifact `create-adr`, `create-module-readme`, `create-requirements-spec`, `create-plan-spec` e `create-tasks-spec` não teriam uma camada intermediária de onde herdar estrutura/formato — ficariam "soltas" direto na Foundation, quebrando a hierarquia de 3 níveis pedida.

---

## Artifact — receitas de geração

| Skill                               | Descrição (frase-ativação)                                                                                                                       | Quem cria                                          | Quem consome (papel + agente)                                                                | Frequência                                                                                               |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `create-rag-endpoint`               | "Crie o endpoint [nome] que segue o padrão RAG (recebe pergunta → busca chunks → monta prompt → chama GPT-4o → responde com fonte)."             | Dev sênior (valida com Tech Lead)                  | Devs, via **GitHub Copilot** e **Claude Code**                                               | Alta — reutilizada a cada novo endpoint RAG (query hoje; possíveis variações futuras)                    |
| `create-integration-test`           | "Crie o teste de integração para o endpoint [nome]."                                                                                             | QA (com Dev sênior)                                | Devs, via **Copilot**/**Claude Code**; revisado por **QA**                                   | Muito alta — 1 por endpoint no mínimo, mais casos de borda (ver test-plan do QA)                         |
| `create-react-card`                 | "Crie o card de resposta do painel web para exibir [conteúdo]."                                                                                  | Dev do painel web (com Product Specialist para UX) | Devs do painel, via **Copilot**                                                              | Média — cards de resposta, histórico, métricas                                                           |
| `create-feedback-form` _(novo)_     | "Crie o formulário de feedback (atendente reporta resposta incorreta)."                                                                          | Dev do painel web (com Product Specialist)         | Devs do painel, via **Copilot**                                                              | Baixa — poucos formulários no projeto, mas alto risco de UX ruim se genérico                             |
| `create-adr` _(novo)_               | "Registre a decisão sobre [tema] como ADR em `/docs/adr/`."                                                                                      | Tech Lead                                          | Tech Lead, Dev sênior, via **Claude Code**; qualquer papel pode propor via **Claude (chat)** | Baixa — só quando há decisão técnica/escopo relevante (ver regra do AGENTS.md, seção Project Management) |
| `create-module-readme` _(novo)_     | "Documente o módulo [nome] (visão geral, como rodar, como testar)."                                                                              | Tech Lead                                          | Devs, via **Copilot**/**Claude Code**                                                        | Baixa — 1 por módulo (5 módulos), atualizado quando a interface do módulo muda                           |
| `create-requirements-spec` _(novo)_ | "Escreva o `requirements.md` do módulo [nome] no formato SDD (outcomes, scope boundaries, constraints, prior decisions, verification criteria)." | Product Specialist                                 | Product Specialist, via **Claude (chat)**; Tech Lead consome para gerar o plan               | Média — 1 por módulo (5), com revisões quando escopo muda (change management, Ex. 2.2 DM)                |
| `create-plan-spec` _(novo)_         | "Converta o `requirements.md` aprovado do módulo [nome] em `plan.md` (approach, technical decisions, dependencies)."                             | Tech Lead                                          | Tech Lead, via **Claude (chat)**; Dev consome para gerar tasks                               | Média — 1 por módulo (5), com revisões pontuais                                                          |
| `create-tasks-spec` _(novo)_        | "Decomponha o `plan.md` do módulo [nome] em `tasks.md` com tasks atômicas (ID, critérios de aceite, dependências, estimativa)."                  | Dev (com apoio do Copilot)                         | Devs, via **Copilot**/**Claude Code**; Tech Lead aprova (Gate 2)                             | Alta — 1 rodada por módulo, mas tasks.md é reaberto a cada sprint/replanejamento                         |

---

## Cobertura vs. lista de artefatos recorrentes

| Artefato recorrente (input do exercício) | Domain                                                    | Artifact                                                            |
| ---------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------- |
| Endpoints Azure Functions RAG            | `azure-functions-endpoint`, `azure-ai-search-integration` | `create-rag-endpoint`                                               |
| Testes de integração                     | `testing-patterns`                                        | `create-integration-test`                                           |
| Componentes React (cards + formulários)  | `react-components`                                        | `create-react-card`, `create-feedback-form`                         |
| Documentação técnica (ADRs, READMEs)     | `technical-documentation`                                 | `create-adr`, `create-module-readme`                                |
| Specs de produto (SDD)                   | `sdd-spec-structure`                                      | `create-requirements-spec`, `create-plan-spec`, `create-tasks-spec` |

Todos os 5 tipos de artefato citados no input têm agora Domain + Artifact correspondentes — nenhum "artefato órfão" sem skill, e nenhuma skill sem artefato real que a justifique.

## Visão de time (criação e consumo não é só-dev)

- **Tech Lead** é o principal criador de Foundation e Domain (é quem detém as ADRs e a visão técnica transversal) — consistente com o Ex. 2.3 do Tech Lead, que já escreve o SKILL.md de `azure-functions-endpoint`.
- **Product Specialist** cria a skill Artifact que gera `requirements.md` — é quem escreve esse artefato na prática (Ex. 2.1 do Product Specialist).
- **QA** cria `testing-patterns` (Domain) e mantém `create-integration-test` (Artifact) — consistente com o Testing Standards do AGENTS.md (Ex. 2.1 do QA).
- **Devs** criam e mantêm as skills mais próximas do código (`create-rag-endpoint`, `create-tasks-spec`, skills de painel web).
- **Delivery Manager** não cria skill técnica, mas é consumidor indireto: `create-tasks-spec` e `sdd-spec-structure` encapsulam o fluxo de governança de specs que ele definiu (Ex. 2.2 do Delivery Manager) — a skill é o mecanismo que faz esse processo ser seguido pelos agentes, não só descrito num documento.

## Frequência — critério usado

Classificação qualitativa (o projeto tem 3 meses, ~6 sprints de 2 semanas, 2 Devs + 1 Tech Lead no código):

- **Muito alta**: consultada em praticamente todo PR/commit de código.
- **Alta**: consultada múltiplas vezes por sprint, ligada a um fluxo central (endpoint, teste, task).
- **Média**: consultada algumas vezes por sprint ou concentrada numa janela do projeto (ex: painel web).
- **Baixa**: consultada poucas vezes no projeto inteiro, mas com alto custo se ausente (ADR, formulário mal desenhado).

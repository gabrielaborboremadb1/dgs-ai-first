# Tasks — Query Endpoint

> Gerado a partir de `plan.md` (Ex. 2.1). Cada task é atômica (um artefato/arquivo por task sempre que possível), com critérios de aceite verificáveis e dependências explícitas para permitir paralelização segura entre desenvolvedores.
>
> Legenda de estimativa: **P** (pequena, <2h) · **M** (média, meio dia) · **G** (grande, dia inteiro ou mais).

---

### QE-001 — Definir tipos de domínio do query endpoint
**Descrição:** Adicionar em `src/shared/types.ts` os tipos `QueryRequest`, `QueryResponse`, `RetrievedChunk` e `SourceDocument` usados por todo o fluxo do endpoint (request recebido, chunk retornado pela busca, resposta final com fonte).
**Critérios de aceite:**
- Tipos exportados e sem uso de `any`.
- `RetrievedChunk` inclui `content`, `sourceDocument`, `score` e metadado de vigência (`isCurrent`/`supersededBy`, conforme ADR-0003).
- `QueryResponse` inclui `answer` e `sourceDocuments` (lista, não singular, pois pode citar mais de um documento).
- Compila sem erros (`tsc --noEmit`) com `strict: true`.
**Dependências:** nenhuma.
**Estimativa:** P

---

### QE-002 — Configuração de ambiente (endpoints e chaves Azure)
**Descrição:** Implementar `src/shared/config.ts` para ler e validar (via Zod) as variáveis de ambiente necessárias: endpoint/chave do Azure OpenAI (embeddings + chat), endpoint/chave/índice do Azure AI Search, e parâmetros do context budget (tokens de system prompt, tokens de chunks, nº de chunks) definidos na ADR-0002.
**Critérios de aceite:**
- Falha de forma explícita e imediata (erro na inicialização, não silenciosa) se uma variável obrigatória estiver ausente.
- Valores de context budget (~4K system, ~8K chunks, 5 chunks) expostos como constantes/config, não hardcoded nos serviços que os consomem.
- Testável isoladamente (não depende de rede).
**Dependências:** nenhuma.
**Estimativa:** P

---

### QE-003 — Custom errors do domínio
**Descrição:** Implementar em `src/shared/errors.ts` as classes de erro específicas do endpoint: `ValidationError`, `SearchServiceError`, `CompletionServiceError`, `EmptyContextError` (nenhum chunk relevante encontrado).
**Critérios de aceite:**
- Cada erro carrega `statusCode` HTTP apropriado (400 para validação, 502/503 para falhas de serviço externo, etc.) para uso posterior no handler.
- Erros distinguíveis por `instanceof` nos testes.
**Dependências:** nenhuma.
**Estimativa:** P

---

### QE-004 — Validação de input (Zod)
**Descrição:** Implementar `src/functions/query/validator.ts` com schema Zod para o body de `POST /api/query` (pergunta do atendente + histórico opcional de até 3 turnos, conforme ADR-0002).
**Critérios de aceite:**
- Rejeita pergunta vazia, pergunta acima de um tamanho máximo razoável, e histórico com mais de 3 turnos.
- Retorna `ValidationError` (QE-003) com mensagem descritiva em caso de falha.
- Coberto por testes unitários (ver QE-013).
**Dependências:** QE-001, QE-003.
**Estimativa:** P

---

### QE-005 — Wrapper de retry com exponential backoff
**Descrição:** Implementar utilitário reutilizável de retry com backoff exponencial para chamadas a serviços Azure (usado por QE-006 e QE-008), incluindo limite de tentativas e jitter.
**Critérios de aceite:**
- Função genérica, sem dependência dos detalhes de Search/OpenAI (recebe uma função assíncrona e políticas de retry como parâmetro).
- Não faz retry em erros não transitórios (ex.: 400 de validação).
- Testável com mocks de função que falha N vezes e depois sucede.
**Dependências:** QE-003.
**Estimativa:** P

---

### QE-006 — Geração de embedding + busca de chunks no Azure AI Search
**Descrição:** Implementar `src/services/search.ts`: gera embedding da pergunta via Azure OpenAI e busca os top-5 chunks mais relevantes no índice do Azure AI Search.
**Critérios de aceite:**
- Usa o wrapper de retry (QE-005) nas duas chamadas externas (embedding e busca).
- Retorna lista tipada de `RetrievedChunk` (QE-001), incluindo metadado de vigência.
- Lança `SearchServiceError` (QE-003) em caso de falha após esgotar retries.
- Lança `EmptyContextError` se a busca não retornar nenhum chunk.
- **Bloqueio externo:** requer o índice do Azure AI Search populado pelo pipeline de ingestão (fora do escopo desta spec) para testes de integração/e2e; testes unitários usam mocks.
**Dependências:** QE-001, QE-002, QE-003, QE-005.
**Estimativa:** M

---

### QE-007 — Montagem do prompt respeitando o context budget
**Descrição:** Implementar `src/services/prompt-builder.ts`: monta o prompt final combinando system prompt (`/prompts/system-prompt.md`), os chunks recuperados, o histórico (≤3 turnos) e a pergunta, respeitando o orçamento de ~4K tokens (system) + ~8K tokens (chunks) definido na ADR-0002.
**Critérios de aceite:**
- Trunca/descarta chunks excedentes (a partir do de menor score) se a soma ultrapassar o budget de tokens, em vez de falhar.
- Instrui explicitamente o modelo a priorizar o documento vigente quando houver chunks conflitantes (ADR-0003).
- Contagem de tokens usa a mesma tokenização do modelo alvo (GPT-4o) ou aproximação documentada.
- **Bloqueio externo:** depende do conteúdo final de `/prompts/system-prompt.md` (versionado à parte); a task pode ser implementada e testada com uma versão placeholder do prompt enquanto isso.
**Dependências:** QE-001, QE-002.
**Estimativa:** M

---

### QE-008 — Chamada de completion ao GPT-4o
**Descrição:** Implementar `src/services/completion.ts`: envia o prompt montado ao Azure OpenAI (GPT-4o) e retorna a resposta bruta do modelo.
**Critérios de aceite:**
- Usa o wrapper de retry (QE-005).
- Aplica timeout configurável.
- Lança `CompletionServiceError` (QE-003) em caso de falha após esgotar retries.
**Dependências:** QE-002, QE-003, QE-005.
**Estimativa:** M

---

### QE-009 — Validação determinística da resposta (harness)
**Descrição:** Implementar `src/services/response-validator.ts`: valida deterministicamente a saída do modelo antes de devolvê-la ao atendente (ex.: resposta cita ao menos um `source_document` presente no contexto enviado; não cita documento marcado como obsoleto como se fosse vigente).
**Critérios de aceite:**
- Recebe a resposta do modelo + os chunks usados como contexto e retorna `valid: boolean` + motivo em caso de falha.
- Cobre pelo menos os dois casos acima com testes unitários.
- Não faz chamada externa (puramente determinística).
**Dependências:** QE-001.
**Estimativa:** M

---

### QE-010 — Montagem da resposta final com fonte
**Descrição:** Implementar `src/functions/query/response-builder.ts`: monta o `QueryResponse` (QE-001) a partir da resposta validada do modelo e dos chunks recuperados, incluindo a lista de `sourceDocuments`.
**Critérios de aceite:**
- Se `response-validator` (QE-009) reportar inválido, retorna resposta de fallback controlada (não expõe erro interno ao atendente) em vez de propagar a resposta não confiável.
- Formato de saída estável e coberto por teste de snapshot/fixture.
**Dependências:** QE-001, QE-009.
**Estimativa:** P

---

### QE-011 — HTTP handler do endpoint (orquestração)
**Descrição:** Implementar `src/functions/query/handler.ts`: Azure Function HTTP trigger `POST /api/query` que orquestra validator → search → prompt-builder → completion → response-validator → response-builder, na ordem descrita no `plan.md`.
**Critérios de aceite:**
- Erros tipados (QE-003) são mapeados para os status HTTP corretos na resposta.
- Log estruturado (pino) emitido em pontos-chave: recebimento da pergunta, chunks recuperados (ids, não conteúdo completo, por volume), latência de cada etapa, erro (se houver).
- Endpoint retorna 200 com `QueryResponse` no caminho feliz.
- Coberto por teste de integração (QE-013) com Search e OpenAI mockados via msw.
**Dependências:** QE-004, QE-006, QE-007, QE-008, QE-010.
**Estimativa:** M

---

### QE-012 — Fixtures de teste (chunks, queries, respostas esperadas)
**Descrição:** Criar `tests/fixtures/chunks.ts`, `tests/fixtures/queries.ts` e `tests/fixtures/expected-responses.ts` com dados sintéticos representativos (incluindo ao menos um cenário de chunks contraditórios/obsoletos, conforme ADR-0003).
**Critérios de aceite:**
- Fixtures tipadas com os tipos de QE-001.
- Usadas por pelo menos um teste unitário e um de integração (QE-013).
**Dependências:** QE-001.
**Estimativa:** P

---

### QE-013 — Testes unitários e de integração do query endpoint
**Descrição:** Escrever testes unitários (`tests/unit/`) para validator, prompt-builder, response-validator e response-builder; e teste de integração (`tests/integration/`) do handler completo com Azure AI Search e Azure OpenAI mockados via msw.
**Critérios de aceite:**
- Cobertura dos casos de erro definidos em QE-003 (validação inválida, falha de search, falha de completion, contexto vazio).
- Teste de integração cobre o caminho feliz e o caso de chunk obsoleto/contraditório (ADR-0003) usando as fixtures de QE-012.
- Todos os testes rodam sem chamadas de rede reais (`npm test` local e no CI).
**Dependências:** QE-004, QE-006, QE-007, QE-008, QE-009, QE-010, QE-011, QE-012.
**Estimativa:** G

---

## Resumo de dependências externas (fora desta spec)

| Dependência | Bloqueia | Origem |
|---|---|---|
| Índice do Azure AI Search populado | QE-006 (testes de integração/e2e) | Spec `pipeline-ingestao` |
| `/prompts/system-prompt.md` finalizado | QE-007 (versão final do prompt) | Versionamento de prompts (fora do código) |

## Ordem sugerida de execução (paralelizável)

1. **Paralelo:** QE-001, QE-002, QE-003
2. **Paralelo:** QE-004, QE-005, QE-012 (após QE-001/QE-003)
3. **Paralelo:** QE-006, QE-007, QE-008 (após QE-002, QE-003, QE-005)
4. QE-009 (após QE-001) → QE-010 (após QE-009)
5. QE-011 (após QE-004, QE-006, QE-007, QE-008, QE-010)
6. QE-013 (após tudo acima)

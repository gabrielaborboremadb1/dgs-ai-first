# Skill: TypeScript Conventions (Foundation)

## Quando esta skill se aplica (frase de ativação)
"Estou gerando ou editando qualquer arquivo `.ts`/`.tsx` deste repositório" — em qualquer camada (Azure Functions, pipeline de ingestão, bot do Teams, painel web, testes). É a primeira skill a ser lida por um agente, antes de qualquer skill Domain ou Artifact.

## Contexto
Esta é a skill-base da hierarquia Foundation → Domain → Artifact: toda skill de nível superior (`azure-functions-endpoint`, `react-components`, `create-rag-endpoint`, etc.) assume que estas convenções já foram aplicadas e não as repete.

Decisões que fundamentam esta skill (ADRs da fase anterior + `tsconfig.json`/`package.json` do projeto):
- `strict: true`, `target: ES2022`, `module: ESNext`, `moduleResolution: Bundler` (ver `tsconfig.json`).
- Zod (`zod`) é a biblioteca de validação padrão do projeto — toda fronteira externa (HTTP, resposta de serviço Azure) passa por um schema Zod.
- O projeto é mantido por desenvolvedores de senioridade mista (1 pleno, 1 sênior) e por agentes de IA (Copilot, Claude Code) ao longo de 3 meses — inconsistência de tipos entre módulos custa mais caro aqui do que em um projeto só-humano, porque agentes reproduzem o padrão que encontram no arquivo mais próximo.

## Regras prescritivas

1. **Nunca usar `any`.** Quando o tipo é genuinamente desconhecido no momento da escrita (ex.: payload bruto de uma API externa antes de validar), usar `unknown` e estreitar o tipo via Zod ou type guard.
2. **Nunca silenciar erro de tipo** com `// @ts-ignore` ou `// @ts-expect-error` sem um comentário explicando por que o erro é inevitável e temporário. Preferir corrigir o tipo.
3. **Tipos de domínio compartilhado vivem em `src/shared/types.ts`.** Não redeclarar o mesmo shape em outro arquivo.
4. **Fronteiras externas (request HTTP, resposta de serviço Azure) são validadas com um schema Zod, e o tipo é derivado do schema com `z.infer`** — nunca um `interface` escrito à mão ao lado de um schema Zod separado descrevendo "a mesma coisa".
5. **`interface`** para shapes de objeto (entidades de domínio, request/response). **`type`** para unions, intersections e utility types.
6. **Nomenclatura:** `PascalCase` para types/interfaces/classes; `camelCase` para variáveis e funções; `UPPER_SNAKE_CASE` só para constantes de configuração verdadeiramente fixas (ex.: limites de retry, budget de tokens).
7. **Toda função exportada tem tipo de retorno explícito** — não confiar em inferência em código que cruza módulos (services, handlers, pipeline).
8. **Erros são sempre instâncias de subclasses de `Error`** definidas pela skill `error-handling` — nunca `throw` de string ou objeto literal.
9. **`export default` é proibido** em `services/`, `pipeline/`, `shared/` e `functions/` — usar named exports (facilita mock em teste e busca de uso no repositório). Permitido apenas em componentes de página React quando exigido pelo bundler.
10. **Preferir union de string literals a `enum`** para estados fechados pequenos (ex.: `"user" | "assistant"`), exceto quando o valor precisa existir como objeto iterável em runtime.
11. **Imports organizados em blocos**, na ordem: (1) built-ins do Node, (2) dependências externas, (3) módulos internos, com `import type` para imports usados só como tipo.

## Exemplos concretos

### DO — tipo derivado de schema Zod, erro tipado, retorno explícito
```typescript
import { z } from "zod";

import { ValidationError } from "../shared/errors.js";

export const QueryRequestSchema = z.object({
  question: z.string().min(1).max(2000),
  history: z
    .array(z.object({ role: z.enum(["user", "assistant"]), content: z.string() }))
    .max(3)
    .optional(),
});

export type QueryRequest = z.infer<typeof QueryRequestSchema>;

export function parseQueryRequest(body: unknown): QueryRequest {
  const result = QueryRequestSchema.safeParse(body);
  if (!result.success) {
    throw new ValidationError(result.error.message);
  }
  return result.data;
}
```

### DON'T — tipo duplicado à mão, `any`, erro como string
```typescript
// Tipo declarado sem relação com o schema real — diverge silenciosamente
// na primeira vez que alguém adicionar um campo em só um dos dois lugares.
export type QueryRequest = {
  question: string;
  history?: any[]; // 'any' esconde o shape real do histórico
};

export function parseQueryRequest(body: any) {
  if (!body.question) {
    throw "question is required"; // sem stack útil, sem statusCode, não é instanceof Error
  }
  return body as QueryRequest; // cast sem validação real de shape
}
```

### DO — imports organizados, `import type`
```typescript
import { randomUUID } from "node:crypto";

import { z } from "zod";

import { searchChunks } from "../services/search.js";
import type { RetrievedChunk } from "../shared/types.js";
```

### DON'T — imports fora de ordem, tipo e valor misturados
```typescript
import { RetrievedChunk, searchChunks } from "../services/search"; // tipo junto do valor
import { z } from "zod";
import { randomUUID } from "node:crypto"; // built-in depois de dependência externa
```

### DO — union de string literal para estado fechado
```typescript
export interface QueryHistoryTurn {
  role: "user" | "assistant";
  content: string;
}
```

### DON'T — `enum` numérico para o mesmo caso
```typescript
export enum Role {
  User,
  Assistant,
}
// Serializa como 0/1 em JSON de log ou payload de API — ilegível em log
// estruturado (pino) e obriga quem lê o log a decorar o mapeamento.
```

## Anti-padrões (o que Copilot/Claude Code geram sem esta skill)

1. **`any` como válvula de escape em payload externo.** Ao integrar com Azure OpenAI/AI Search, é comum o agente tipar a resposta bruta como `any` "temporariamente". Isso nunca é revertido no PR seguinte. Consequência real neste projeto: um `RetrievedChunk` mal tipado pode perder silenciosamente o campo `isCurrent` (ADR-0003 — metadado de vigência), e o compilador não acusaria nada.
2. **Tipo duplicado entre schema de validação e tipo de domínio.** O agente escreve um `interface` de request em `types.ts` e, em outro arquivo, um `z.object` parecido "na mão" para validar — em vez de derivar um do outro com `z.infer`. Os dois divergem no primeiro PR que adiciona um campo em só um dos lugares.
3. **`throw` de string ou objeto literal.** Sem conhecer a skill `error-handling`, o agente lança `throw "mensagem"` ou `throw { message: "..." }`. Quebra o mapeamento de erro → status HTTP feito no handler.
4. **Cast (`as Tipo`) para calar o compilador**, especialmente no retorno de `fetch`/SDK do Azure, em vez de validar com Zod. Esconde um bug real de shape em vez de falhar cedo e de forma legível.
5. **`export default` em módulos de serviço** (`export default class SearchService`). Dificulta `vi.mock` em teste e busca de uso (`grep`) no repositório — dois problemas concretos neste projeto, que depende de mocks de serviço em quase todo teste de integração.
6. **Função exportada sem tipo de retorno explícito.** Uma mudança interna no corpo da função muda silenciosamente o contrato consumido por outro módulo (ex.: handler consumindo `search.ts`) sem que o compilador acuse no ponto de chamada.
7. **`enum` do TypeScript para estados fechados pequenos** (papel do turno, tier de cliente). Gera valor numérico ou objeto extra em runtime onde uma union de string literal já resolveria com menos código gerado e melhor legibilidade em log estruturado e payload JSON.

## Dependências
Nenhuma — é a skill-base da Foundation. Todas as skills Domain e Artifact do projeto assumem que esta foi lida primeiro.

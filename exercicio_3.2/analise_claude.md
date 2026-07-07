## Revisão crítica — `feedback-handler.ts`

O código funciona no caminho feliz, mas tem vários problemas que vão gerar dor de cabeça em produção. Vou dividir por gravidade.

### 🔴 Críticos

**1. Zero tratamento de erro**
`request.json()`, `container.items.create()` e a própria inicialização do `CosmosClient` podem lançar exceção a qualquer momento (JSON malformado, credencial inválida, Cosmos fora do ar, throttling 429). Sem `try/catch`, a function vai estourar uma 500 genérica sem controle nenhum sobre o retorno, e sem logar o motivo real do erro.

**2. Nenhuma validação de entrada**
`body` é `any` e todos os campos são usados sem checagem. Isso significa:
- `queryId`, `rating`, `attendantEmail` podem vir `undefined` e serem gravados assim no banco;
- `rating` pode ser qualquer coisa (string, número fora de 1–5, objeto);
- Não há checagem de formato de e-mail;
- Nenhum limite de tamanho para `comment` (alguém pode mandar payload de 10MB).

Usar `as any` aqui anula completamente a vantagem de estar em TypeScript.

**3. `CosmosClient` recriado a cada requisição**
```ts
const { CosmosClient } = require('@azure/cosmos');
const client = new CosmosClient(process.env.COSMOS_CONNECTION_STRING);
```
Isso recria a conexão (e reautentica) em toda invocação. Em Azure Functions o ideal é inicializar o client **uma vez fora do handler** (nível de módulo), reaproveitando a conexão entre invocações do mesmo worker — impacta latência e pode esgotar conexões sob carga.

**4. Sem autenticação/autorização**
Não há `authLevel` definido explicitamente em `app.http`, nem qualquer verificação de quem está enviando o feedback. Qualquer pessoa com a URL pode gravar dados arbitrários no Cosmos DB (incluindo se passar por um "attendantEmail" que não é dela).

### 🟠 Importantes

**5. Log de dados pessoais em texto claro**
```ts
console.log('Feedback recebido:', JSON.stringify(feedback));
```
Isso joga e-mail e comentário (potencialmente PII) direto nos logs do Application Insights/Log Analytics, sem mascaramento. Vale revisar à luz da LGPD — logs geralmente têm retenção e acesso mais amplo do que o banco de dados em si.

**6. `require()` misturado com `import`**
O arquivo já usa `import` no topo, mas troca para `require('@azure/cosmos')` no meio da função. Isso é resíduo de geração automática (Copilot) e deveria ser um único `import { CosmosClient } from '@azure/cosmos'` no topo do arquivo.

**7. Resposta sem `Content-Type` e sem padrão de erro**
Retorna sempre `{ status: 200, body: 'OK' }`, mesmo que a lógica de erro venha a existir depois. Não há um contrato de resposta (ex: JSON com `{ success: true, id: ... }`), o que dificulta o consumo por um front-end.

### 🟡 Menores / manutenibilidade

- Nome do banco (`'novatech'`) e do container (`'feedbacks'`) estão hardcoded — deveriam vir de variável de ambiente, facilitando dev/staging/prod.
- Falta um `id` explícito no documento (o Cosmos gera um GUID automaticamente se não for passado, mas é melhor ser explícito e guardar controle sobre isso).
- Não existe correlação/rastreamento (`request-id`) para depurar um feedback específico depois nos logs.
- `rating` não tem tipo definido — deveria ser uma union type (`1 | 2 | 3 | 4 | 5`) ou validado com uma lib como `zod`.

### Sugestão de reescrita

```ts
// feedback-handler.ts
import { app, HttpRequest, HttpResponseInit, InvocationContext } from '@azure/functions';
import { CosmosClient } from '@azure/cosmos';
import { z } from 'zod';

// Client inicializado uma única vez, reaproveitado entre invocações
const cosmosClient = new CosmosClient(process.env.COSMOS_CONNECTION_STRING!);
const container = cosmosClient
  .database(process.env.COSMOS_DATABASE ?? 'novatech')
  .container(process.env.COSMOS_CONTAINER ?? 'feedbacks');

const feedbackSchema = z.object({
  queryId: z.string().min(1),
  rating: z.number().int().min(1).max(5),
  comment: z.string().max(2000).optional(),
  attendantEmail: z.string().email(),
});

export async function feedbackHandler(
  request: HttpRequest,
  context: InvocationContext
): Promise<HttpResponseInit> {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return { status: 400, jsonBody: { error: 'JSON inválido' } };
  }

  const parsed = feedbackSchema.safeParse(payload);
  if (!parsed.success) {
    return { status: 400, jsonBody: { error: 'Payload inválido', details: parsed.error.flatten() } };
  }

  const feedback = {
    ...parsed.data,
    timestamp: new Date().toISOString(),
  };

  context.log('Feedback recebido', { queryId: feedback.queryId, rating: feedback.rating });
  // evite logar comment/attendantEmail em texto puro

  try {
    const { resource } = await container.items.create(feedback);
    return { status: 201, jsonBody: { success: true, id: resource?.id } };
  } catch (err) {
    context.error('Falha ao gravar feedback no Cosmos', err);
    return { status: 500, jsonBody: { error: 'Erro interno ao salvar feedback' } };
  }
}

app.http('feedback', {
  methods: ['POST'],
  authLevel: 'function', // ou 'anonymous' com validação/rate limit próprios — decisão consciente
  route: 'feedback',
  handler: feedbackHandler,
});
```

Principais mudanças: validação com `zod`, client Cosmos singleton, tratamento de erro em cada etapa, `authLevel` explícito, resposta em JSON com status semântico (201 para criação), e log sem expor PII completa.

Quer que eu aprofunde em algum ponto específico — por exemplo, estratégia de autenticação para esse endpoint, ou como estruturar retry/idempotência para o Cosmos?
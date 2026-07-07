# Implementação do handler

```typescript
import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { CosmosClient } from "@azure/cosmos";

import { logger } from "../../shared/logger.js";
import { FeedbackInputSchema } from "./validator.js";

// Client inicializado uma única vez no nível de módulo e reaproveitado entre invocações
// do mesmo worker — recriar a conexão a cada requisição (como a versão gerada pelo
// Copilot fazia) custa latência e pode esgotar conexões sob carga.
const cosmosClient = new CosmosClient(process.env.COSMOS_CONNECTION_STRING ?? "");
const feedbackContainer = cosmosClient
  .database(process.env.COSMOS_DATABASE ?? "novatech")
  .container(process.env.COSMOS_CONTAINER_FEEDBACK ?? "feedbacks");

export async function feedbackHandler(
  request: HttpRequest,
  context: InvocationContext,
): Promise<HttpResponseInit> {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return { status: 400, jsonBody: { error: "JSON inválido" } };
  }

  const parsed = FeedbackInputSchema.safeParse(payload);
  if (!parsed.success) {
    // Loga só os nomes dos campos com problema, nunca o payload bruto — que pode
    // conter e-mail/comentário do atendente (ver AGENTS.md: nunca logar dados pessoais).
    const fields = parsed.error.issues.map((issue) => issue.path.join(".")).join(", ");
    logger.warn(
      { invocationId: context.invocationId, fields },
      "feedback-handler: payload rejeitado pela validação",
    );
    return { status: 400, jsonBody: { error: "Payload inválido", fields } };
  }

  const feedback = {
    id: crypto.randomUUID(),
    ...parsed.data,
    timestamp: new Date().toISOString(),
  };

  // Loga só o necessário para rastrear o feedback (id, queryId, rating) — nunca
  // attendantEmail nem comment, que são dados pessoais (ver AGENTS.md).
  logger.info(
    { invocationId: context.invocationId, id: feedback.id, queryId: feedback.queryId, rating: feedback.rating },
    "feedback-handler: feedback recebido",
  );

  try {
    const { resource } = await feedbackContainer.items.create(feedback);
    return { status: 201, jsonBody: { success: true, id: resource?.id } };
  } catch (err) {
    logger.error(
      { invocationId: context.invocationId, id: feedback.id, err },
      "feedback-handler: falha ao gravar feedback no Cosmos",
    );
    return { status: 500, jsonBody: { error: "Erro interno ao salvar feedback" } };
  }
}

app.http("feedback", {
  methods: ["POST"],
  authLevel: "function",
  route: "feedback",
  handler: feedbackHandler,
});
```
## 1. Estados inválidos representáveis em `RetrievedChunk` (linhas 22-23)

Nada impede `{ isCurrent: true, supersededBy: "doc-42" }` (documento marcado como vigente e como substituído) ou
`{ isCurrent: false }` sem indicar por qual documento foi substituído. Isso é justamente o metadado de vigência da
ADR-0003, a peça central do tratamento de contradições, e o tipo atual não impede o estado contraditório que a
própria ADR existe para resolver. Deveria ser uma union discriminada:

```typescript
type Vigencia =
  | { isCurrent: true }
  | { isCurrent: false; supersededBy: string };

interface RetrievedChunk {
  content: string;
  sourceDocument: SourceDocument;
  score: number;
  vigencia: Vigencia;
}
```

`SourceDocument.version` (linha 15) e a vigência do chunk (`isCurrent`/`supersededBy`) são fontes de verdade separadas e
não relacionadas no tipo, então dá pra ter versões divergindo do status de vigência sem o compilador acusar nada.
Se resolver utilizar a union discriminada, vale mover essa lógica de vigência para perto de `version` ou documentar
a relação entre os dois campos.

## 2. `QueryResponse` não distingue resposta fundamentada de fallback

A QE-010 exige explicitamente: "Se response-validator reportar inválido, retorna resposta de fallback
controlada (...) em vez de propagar a resposta não confiável." Mas QueryResponse (linhas 26-29) tem o mesmo
shape para os dois casos:

```typescript
interface QueryResponse {
  answer: string;
  sourceDocuments: SourceDocument[];
}
```

Do jeito que está, um bot no Teams não consegue diferenciar "resposta fundamentada na documentação" de
"não encontrei resposta confiável", que é exatamente a promessa central do produto para a NovaTech (respostas
com indicação de fonte, não respostas genéricas). Falta algo como `status: "answered" | "fallback"` ou
`sourceDocuments: SourceDocument[]` vazio só sendo suficiente se o consumidor souber tratar lista vazia como
sinal, o que hoje não está documentado nem tipado.

## 3. Nenhum identificador correlacionável com feedback

`QueryResponse` não tem `id`/`queryId`. A estrutura do repo já prevê `feedback-card.ts` e uma spec `feedback-api`,
ou seja, o atendente vai dar feedback sobre uma resposta específica. Sem um id na resposta, não há como o
`feedback-api` referenciar qual resposta está sendo avaliada. Isso normalmente só aparece depois, quando alguém
for implementar a spec `feedback-api` e perceber que falta a chave estrangeira, então vale resolver agora, no tipo
compartilhado.

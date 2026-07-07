# Code Review — `response-validator.ts` (gerado pelo GitHub Copilot)

**Exercício:** 3.1 — Structured output e verificações determinísticas (Desenvolvedor)
**Arquivo revisado:** [`src/services/response-validator.ts`](../../src/services/response-validator.ts)
**Testes:** [`tests/unit/response-validator.test.ts`](../../tests/unit/response-validator.test.ts)
**Revisor:** Claude (chat), a pedido do desenvolvedor

## Contexto

O Copilot gerou o `response-validator.ts` para aplicar, via código (verificação determinística), os dois guardrails formalizados pelo Product Specialist:

1. Toda resposta **DEVE** conter `source_document` — se ausente ou vazio, a resposta é rejeitada e substituída pela mensagem padrão segura.
2. Respostas que mencionam **"carga perigosa"** junto de **"devolução"** **DEVEM** conter a negativa — se afirmarem que a devolução é possível, a resposta é bloqueada (ver [POL-001, seção 3.2](../novatech/POL-001-politica-devolucao.md)).

A revisão teve como objetivo responder duas perguntas guia: *o schema aceita campos extras?* e *o regex de "carga perigosa + devolução" cobre variações?* — e, mais amplamente, testar o código com casos reais em vez de aceitar o comentário do próprio Copilot como prova de correção.

## Prompt (probabilístico) vs. código (determinístico)

O [`system-prompt.md`](../../prompts/system-prompt.md) atual (v1) instrui o modelo apenas com *"Use apenas as informações dos documentos fornecidos. Cite a fonte. Se não souber, diga que não sabe."* — não há nenhuma menção explícita à exceção de carga perigosa nem qualquer garantia de formato. Mesmo que houvesse, uma instrução em prompt é **probabilística**: pedir ao modelo para sempre citar a fonte ou sempre negar a devolução de carga perigosa reduz a chance de erro, mas não a elimina — é exatamente o que os testes internos já mostraram (12% de respostas incorretas, fonte ausente quando o modelo "esquece").

O `response-validator.ts` existe para não depender dessa promessa. Ele não lê nem confia no que o prompt pediu — ele **verifica o que o modelo de fato devolveu**, depois do fato, contra regras fixas:

- `source_document` ausente/vazio → sempre rejeitado, independente do que o prompt pedia.
- "carga perigosa" + devolução sem negativa → sempre bloqueado, independente do que o prompt pedia.
- Campo fora do schema → sempre rejeitado (`.strict()`).

Essa é a diferença de camada: o prompt tenta induzir o comportamento certo (camada probabilística, sem garantia); o `response-validator.ts` é a camada de código que **garante** o resultado, porque roda de forma determinística sobre o output já gerado — o mesmo texto sempre produz o mesmo veredito, não importa o quão "criativo" o modelo tenha sido ao formular a frase. Por isso o módulo abre com um comentário explícito sobre esse contrato (linhas 5-9 do arquivo).

## Metodologia

Em vez de inspecionar o código apenas por leitura, cada suspeita foi confirmada executando o regex/stem isoladamente em Node e chamando `validateResponse()` com payloads que reproduzem frases plausíveis de um atendente ou do modelo (incluindo a linguagem exata usada na própria POL-001). Só entrou na lista de "problema" o que falhou de fato.

## Problemas encontrados

### 1. (Crítico) `RETURN_STEM` não cobre as formas verbais de "devolver" — o guardrail de carga perigosa podia nunca disparar

**Onde:** `RETURN_STEM = "devolu"`, usado em `sentence.includes(RETURN_STEM)`.

O comentário original afirmava que o stem *"cobre devolução, devolvida, devolver, devolvido, devoluções"*. Isso é falso — `"devolu"` é a raiz de **devolu**ção/**devolu**ções, mas as formas verbais usam a raiz **devolv**-:

```js
"devolução".includes("devolu")  // true
"devolver".includes("devolu")   // false
"devolvida".includes("devolu")  // false
"devolvido".includes("devolu")  // false
```

**Impacto:** uma resposta como *"Sim, pode devolver a carga perigosa sem problema."* menciona "carga perigosa", mas a sentença não era reconhecida como "sentença de devolução" — `returnSentences` ficava vazio e a função retornava `false` (sem violação). **A resposta perigosa passava validada.** Este era o bug mais grave do arquivo: o guardrail #2 podia ser contornado com uma escolha de palavra plausível do próprio modelo, não um ataque deliberado.

**Correção:** raiz reduzida para `"devol"`, comum tanto à forma nominal (`devol` + `ução`) quanto às formas verbais (`devol` + `ver/vido/vida/veu/vendo`).

```ts
// "devol": raiz comum a "devolução/devoluções" (devol+ução) E às formas verbais
// "devolver/devolvido/devolvida/devolve/devolveu" (devol+ver/vido/vida/...). O stem
// "devolu" usado anteriormente não cobria as formas verbais (ex.: "devolver" não contém
// "devolu"), deixando o guardrail inativo para essas frases.
const RETURN_STEM = "devol";
```

### 2. `DANGEROUS_CARGO_TERM` era uma string literal no singular — não cobria o plural usado na própria POL-001

**Onde:** `const DANGEROUS_CARGO_TERM = "carga perigosa";` com `normalized.includes(DANGEROUS_CARGO_TERM)`.

A POL-001 usa o termo no **plural** ("*Cargas perigosas classificadas nas classes 1 a 6 da ANTT...*"). Testando:

```js
"cargas perigosas não são elegíveis para devolução".includes("carga perigosa") // false
```

**Impacto:** qualquer resposta do modelo que parafraseasse a política usando o plural (o mais natural, já que é a forma do próprio documento-fonte) escapava do guardrail inteiro — a checagem nem chegava a procurar sentenças de devolução.

**Correção:** substituição por regex que aceita singular/plural em ambas as palavras:

```ts
// "carga(s) perigosa(s)": a POL-001 usa o plural ("Cargas perigosas classificadas...").
const DANGEROUS_CARGO_PATTERN = /cargas?\s+perigosas?/;
```

### 3. `NEGATION_TERMS` não reconhecia "negada/negado/negar" — respostas corretas eram bloqueadas por engano

**Onde:** `const NEGATION_TERMS = ["não", "nao", "vedad", "proibid", "exceção", "excecao"];`

Uma resposta correta e segura como *"A devolução de carga perigosa é **negada** pela política."* não contém nenhum dos termos da lista — não há "não", "vedad", "proibid" nem "exceção" na sentença. O `.every()` falhava e a resposta era marcada como **violação**, mesmo estando certa.

**Impacto:** falso positivo — não é um risco de segurança (o guardrail erra para o lado seguro, bloqueando e caindo no fallback), mas gera atrito: respostas corretas do atendente/modelo são descartadas sem motivo, forçando reformulações artificiais só para escapar do filtro.

**Correção:** adicionado o stem `"nega"` à lista (cobre nega, negam, negada, negado, negar, negação, negativa — sem colidir com palavras não relacionadas, como "negligência", que não contém a substring "nega").

```ts
const NEGATION_TERMS = ["não", "nao", "vedad", "proibid", "exceção", "excecao", "nega"];
```

> **Limitação conhecida (não corrigida):** a checagem de negação é por presença de termo na sentença, não por proximidade/semântica. Uma dupla negação adversarial como *"não podemos negar a devolução da carga perigosa"* (que na verdade **permite** a devolução) contém "não" e passaria a checagem. Ficou fora do escopo desta correção por exigir análise sintática além de string matching; registrado aqui para uma iteração futura do guardrail.

### 4. Schema Zod sem `.strict()` — campos extras eram descartados silenciosamente em vez de reprovar

**Onde:** `z.object({ answer, source_document, confidence_score })` sem `.strict()`.

Por padrão, `z.object()` no Zod usa o modo `strip`: chaves não declaradas no schema são **removidas silenciosamente** do objeto validado, e a validação passa como se elas nunca tivessem existido. Isso significa que um payload com um campo inesperado (por exemplo, o modelo "vazando" uma instrução, um campo de debug, ou uma tentativa de contornar o formato esperado) é aceito sem nenhum sinal de alerta.

**Impacto:** o harness perde a chance de tratar "o modelo não respeitou o formato esperado" como um evento a ser logado/rejeitado — o que é exatamente o tipo de sinal que um sistema de structured output deveria capturar.

**Correção:** adicionado `.strict()`, que faz o Zod reprovar a validação (`Unrecognized key(s) in object: '...'`) quando há chaves além de `answer`, `source_document` e `confidence_score`.

```ts
.strict()
```

## Validação das correções

Casos de teste executados manualmente contra `validateResponse()` após a correção (além da suíte `vitest` existente, que continua passando com os 6 testes originais):

| Caso | Antes da correção | Depois da correção |
|---|---|---|
| `"Sim, pode devolver a carga perigosa sem problema."` | ✅ **passava** (bug crítico) | ❌ bloqueada — `GUARDRAIL_DANGEROUS_CARGO_RETURN` |
| `"Sim, cargas perigosas podem ser devolvidas normalmente."` | ✅ **passava** (bug) | ❌ bloqueada — `GUARDRAIL_DANGEROUS_CARGO_RETURN` |
| `"A devolução de carga perigosa é negada pela política."` | ❌ bloqueada por engano (falso positivo) | ✅ aceita |
| Payload com campo extra (`extra_field`) | ✅ aceito, campo descartado | ❌ rejeitado — `Unrecognized key(s) in object: 'extra_field'` |

## Resumo

| # | Problema | Categoria | Severidade |
|---|---|---|---|
| 1 | Stem `"devolu"` não cobre "devolver/devolvido/devolvida" | Bug de cobertura no guardrail #2 | **Crítico** — bypass do guardrail |
| 2 | Termo de carga perigosa não cobre plural | Bug de cobertura no guardrail #2 | Alto — bypass do guardrail |
| 3 | Lista de negação não cobre "negada/negado/negar" | Bug de cobertura (falso positivo) | Médio — UX/atrito, não é risco de segurança |
| 4 | Schema sem `.strict()` | Robustez do structured output | Médio — perde sinal de payload fora do formato esperado |

Os quatro problemas foram corrigidos diretamente em `src/services/response-validator.ts`. Nenhum teste existente foi alterado; todos continuam passando após as correções.

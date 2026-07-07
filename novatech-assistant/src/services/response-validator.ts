import { z } from "zod";

import { logger } from "../shared/logger.js";

// O system prompt (ver prompts/system-prompt.md) PEDE ao modelo que cite a fonte e que
// negue devolução de carga perigosa — mas isso é probabilístico: nada impede o modelo de
// "esquecer" a instrução. Este módulo é o backstop determinístico: não confia no que o
// prompt pediu, valida o que o modelo de fato retornou, e bloqueia/substitui a resposta
// quando o formato ou os guardrails não são respeitados.

const GUARDRAIL_SOURCE_DOCUMENT_REQUIRED = "GUARDRAIL_SOURCE_DOCUMENT_REQUIRED";
const GUARDRAIL_DANGEROUS_CARGO_RETURN = "GUARDRAIL_DANGEROUS_CARGO_RETURN";

// "carga(s) perigosa(s)": a POL-001 usa o plural ("Cargas perigosas classificadas...").
const DANGEROUS_CARGO_PATTERN = /cargas?\s+perigosas?/;
// "devol": raiz comum a "devolução/devoluções" (devol+ução) E às formas verbais
// "devolver/devolvido/devolvida/devolve/devolveu" (devol+ver/vido/vida/...). O stem
// "devolu" usado anteriormente não cobria as formas verbais (ex.: "devolver" não contém
// "devolu"), deixando o guardrail inativo para essas frases.
const RETURN_STEM = "devol";
const NEGATION_TERMS = ["não", "nao", "vedad", "proibid", "exceção", "excecao", "nega"];

// POL-001 nega devolução de carga perigosa. Como o texto do modelo é livre, exige-se que
// TODA sentença que mencione devolução também contenha uma negação — na dúvida, bloqueia
// em vez de arriscar confirmar ao cliente que a devolução é possível.
function violatesDangerousCargoReturnGuardrail(answer: string): boolean {
  const normalized = answer.toLowerCase();
  if (!DANGEROUS_CARGO_PATTERN.test(normalized)) {
    return false;
  }

  const returnSentences = normalized
    .split(/(?<=[.!?])\s+/)
    .filter((sentence) => sentence.includes(RETURN_STEM));

  if (returnSentences.length === 0) {
    return false;
  }

  return !returnSentences.every((sentence) =>
    NEGATION_TERMS.some((term) => sentence.includes(term)),
  );
}

export const StructuredResponseSchema = z
  .object({
    answer: z.string().min(1),
    // undefined é normalizado para "" para que campo ausente e campo vazio caiam no
    // mesmo motivo de rejeição (GUARDRAIL_SOURCE_DOCUMENT_REQUIRED) no log.
    source_document: z.preprocess(
      (value) => (value === undefined ? "" : value),
      z.string().min(1, GUARDRAIL_SOURCE_DOCUMENT_REQUIRED),
    ),
    confidence_score: z.number().min(0).max(1),
  })
  // .strict(): campos extras não previstos (ex.: instruções injetadas pelo modelo em um
  // campo adicional) devem reprovar a validação em vez de serem silenciosamente descartados.
  .strict()
  .refine((data) => !violatesDangerousCargoReturnGuardrail(data.answer), {
    message: GUARDRAIL_DANGEROUS_CARGO_RETURN,
    path: ["answer"],
  });

export type StructuredResponse = z.infer<typeof StructuredResponseSchema>;

export interface ResponseValidationResult {
  isValid: boolean;
  response: StructuredResponse;
  rejectionReason?: string;
}

const FALLBACK_RESPONSE: StructuredResponse = {
  answer:
    "Não foi possível confirmar essa informação com segurança nas fontes oficiais. Encaminhe a dúvida a um responsável antes de repassar uma resposta ao cliente.",
  source_document: "N/A",
  confidence_score: 0,
};

export function validateResponse(rawResponse: unknown): ResponseValidationResult {
  const result = StructuredResponseSchema.safeParse(rawResponse);

  if (!result.success) {
    const rejectionReason = result.error.issues.map((issue) => issue.message).join("; ");
    // Loga apenas o motivo (código do guardrail), nunca o conteúdo bruto da resposta —
    // ver AGENTS.md: incidente anterior de log de dado sensível do atendente.
    logger.warn({ rejectionReason }, "response-validator: resposta rejeitada pelo harness");
    return { isValid: false, response: FALLBACK_RESPONSE, rejectionReason };
  }

  return { isValid: true, response: result.data };
}

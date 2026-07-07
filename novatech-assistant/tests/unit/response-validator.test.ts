import { describe, expect, it } from "vitest";

import { validateResponse } from "../../src/services/response-validator.js";

describe("validateResponse", () => {
  it("aceita uma resposta válida que respeita o schema e os guardrails", () => {
    const result = validateResponse({
      answer: "O prazo de devolução padrão é de 7 dias úteis.",
      source_document: "POL-001",
      confidence_score: 0.9,
    });

    expect(result.isValid).toBe(true);
    expect(result.response.source_document).toBe("POL-001");
  });

  it("rejeita resposta sem source_document e retorna a resposta padrão segura", () => {
    const result = validateResponse({
      answer: "O prazo de devolução padrão é de 7 dias úteis.",
      source_document: "",
      confidence_score: 0.9,
    });

    expect(result.isValid).toBe(false);
    expect(result.rejectionReason).toContain("GUARDRAIL_SOURCE_DOCUMENT_REQUIRED");
    expect(result.response).toEqual(
      expect.objectContaining({ source_document: "N/A", confidence_score: 0 }),
    );
  });

  it("rejeita resposta com source_document ausente do payload", () => {
    const result = validateResponse({
      answer: "O prazo de devolução padrão é de 7 dias úteis.",
      confidence_score: 0.9,
    });

    expect(result.isValid).toBe(false);
    expect(result.rejectionReason).toContain("GUARDRAIL_SOURCE_DOCUMENT_REQUIRED");
  });

  it("bloqueia resposta que afirma devolução possível para carga perigosa", () => {
    const result = validateResponse({
      answer: "Sim, é possível fazer a devolução de carga perigosa normalmente.",
      source_document: "POL-001",
      confidence_score: 0.8,
    });

    expect(result.isValid).toBe(false);
    expect(result.rejectionReason).toContain("GUARDRAIL_DANGEROUS_CARGO_RETURN");
  });

  it("permite resposta sobre carga perigosa quando a negativa está presente", () => {
    const result = validateResponse({
      answer: "Carga perigosa não é elegível para devolução pelo processo padrão.",
      source_document: "POL-001",
      confidence_score: 0.95,
    });

    expect(result.isValid).toBe(true);
  });

  it("rejeita confidence_score fora do intervalo [0, 1]", () => {
    const result = validateResponse({
      answer: "O prazo de devolução padrão é de 7 dias úteis.",
      source_document: "POL-001",
      confidence_score: 1.5,
    });

    expect(result.isValid).toBe(false);
  });
});

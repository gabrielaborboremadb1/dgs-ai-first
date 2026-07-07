import { z } from "zod";

// Contrato de input do endpoint de feedback. .strict(): payload com campos além dos
// previstos (ex.: um campo de debug vazado pelo cliente) é rejeitado em vez de aceito
// silenciosamente — mesmo raciocínio do structured output em response-validator.ts.
export const FeedbackInputSchema = z
  .object({
    queryId: z.string().min(1),
    rating: z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4), z.literal(5)]),
    comment: z.string().max(2000).optional(),
    attendantEmail: z.string().email(),
  })
  .strict();

export type FeedbackInput = z.infer<typeof FeedbackInputSchema>;

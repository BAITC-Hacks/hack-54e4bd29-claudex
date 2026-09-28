import { z } from "zod";

const optionalDate = z.string().nullable();

export const copilotFactSchema = z.object({
  id: z.string().min(1),
  metric_code: z.string().min(1),
  label: z.string().min(1),
  value: z.number().finite(),
  unit: z.string().min(1),
  direction: z.enum(["INCREASE", "DECREASE"]),
  period_start: optionalDate,
  period_end: optionalDate,
  source: z.string().min(1),
}).strict();

export type CopilotFact = z.infer<typeof copilotFactSchema>;

export const copilotResponseSchema = z.object({
  signal_id: z.string().uuid(),
  signal_version: z.number().int().positive(),
  title: z.string(),
  explanation: z.string().min(1),
  fact_ids: z.array(z.string()).min(1),
  facts: z.array(copilotFactSchema).min(1),
  evaluation_period_start: optionalDate,
  evaluation_period_end: optionalDate,
  reference_period_start: optionalDate,
  reference_period_end: optionalDate,
  data_current: z.boolean(),
  data_watermark_at: optionalDate,
  limitations: z.array(z.string()),
  generated_at: z.string(),
  request_id: z.string().nullable(),
  llm_generated: z.literal(true),
  provider: z.string(),
  model: z.string(),
}).strict().superRefine((result, context) => {
  const available = new Set(result.facts.map((fact) => fact.id));
  if (new Set(result.fact_ids).size !== result.fact_ids.length ||
      result.fact_ids.some((id) => !available.has(id))) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Unknown or duplicate fact ID", path: ["fact_ids"] });
  }
});

export type CopilotResponse = z.infer<typeof copilotResponseSchema>;

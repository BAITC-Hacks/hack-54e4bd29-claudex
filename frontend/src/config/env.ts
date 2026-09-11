import { z } from "zod";

/**
 * Публичная конфигурация фронтенда.
 *
 * Проверяется схемой при загрузке модуля: опечатка в переменной окружения
 * должна обнаруживаться при сборке, а не превращаться в `undefined`
 * внутри адреса запроса.
 *
 * Сюда попадают только значения, которые допустимо отдать браузеру.
 * Секретов среди них нет и быть не может: всё с префиксом NEXT_PUBLIC_
 * встраивается в клиентский код.
 */
const environmentSchema = z.object({
  apiBaseUrl: z.string().min(1, "NEXT_PUBLIC_API_BASE_URL не задан"),
  appEnv: z.enum(["local", "dev", "staging", "production"]).default("local"),
  disclaimerEnabled: z.boolean().default(true),
});

export type AppEnvironment = z.infer<typeof environmentSchema>;

function readEnvironment(): AppEnvironment {
  const parsed = environmentSchema.safeParse({
    apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1",
    appEnv: process.env.NEXT_PUBLIC_APP_ENV ?? "local",
    disclaimerEnabled: process.env.NEXT_PUBLIC_DISCLAIMER_ENABLED !== "false",
  });

  if (!parsed.success) {
    const issues = parsed.error.issues.map((issue) => issue.message).join("; ");
    throw new Error(`Некорректная конфигурация фронтенда: ${issues}`);
  }

  return parsed.data;
}

export const env: AppEnvironment = readEnvironment();

/**
 * Обязательная оговорка о характере расчётов.
 *
 * Текст прогнозов и сценариев приходит с сервера вместе с данными
 * (API.md, раздел 5.2). Эта константа относится к самому приложению
 * и показывается в подвале, а не заменяет серверные оговорки.
 */
export const DECISION_SUPPORT_NOTICE =
  "MedSignal — система поддержки принятия решений. Расчёты носят справочный " +
  "характер. Решение принимает уполномоченный сотрудник.";

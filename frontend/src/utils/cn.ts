import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Объединение классов Tailwind с разрешением конфликтов.
 * Псевдоним `utils` в components.json указывает сюда, поэтому компоненты
 * shadcn/ui подключаются без правок.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

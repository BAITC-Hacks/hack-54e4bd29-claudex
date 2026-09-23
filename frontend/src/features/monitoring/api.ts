import { isLocalResearchHost } from './local-research';

export async function pilotApi<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  if (!isLocalResearchHost()) throw new Error('Исследовательский API доступен только в явном локальном режиме');
  const response = await fetch(`/api/pilot/${path}`, {
    method, cache: 'no-store',
    headers: {'Content-Type': 'application/json', 'X-MedSignal-Demo': '1'},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'Сервис временно недоступен');
  }
  return response.json();
}
export const number = (value: number) => new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 1}).format(value);
export const day = (value: string) => new Date(value+'T00:00:00').toLocaleDateString('ru-RU');
export const severity = {WARNING: 'Умеренная', HIGH: 'Высокая', CRITICAL: 'Критическая'};
export const status = {NEW: 'Новое', IN_PROGRESS: 'В работе', CLOSED: 'Закрыто'};

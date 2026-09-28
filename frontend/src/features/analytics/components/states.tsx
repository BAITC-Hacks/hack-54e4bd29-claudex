import { AlertCircle, Inbox } from "lucide-react";

export function LoadingState({ label = "Загрузка аналитики…" }: { label?: string }) { return <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground" aria-live="polite">{label}</div>; }
export function EmptyState({ label = "За выбранный период данных нет." }: { label?: string }) { return <div className="rounded-lg border border-dashed p-8 text-center"><Inbox className="mx-auto h-6 w-6 text-muted-foreground" aria-hidden="true" /><p className="mt-2 text-sm text-muted-foreground">{label}</p></div>; }
export function ErrorState({ label = "Не удалось получить данные. Повторите позже." }: { label?: string }) { return <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-5 text-sm text-destructive" role="alert"><AlertCircle className="mr-2 inline h-4 w-4" aria-hidden="true" />{label}</div>; }

import { AlertTriangle, CheckCircle2 } from "lucide-react";

export function QualityIndicator({ status, warnings }: { status: string; warnings: number }) {
  const clean = status === "LOADED" && warnings === 0;
  return <span className={`inline-flex items-center gap-1.5 text-sm ${clean ? "text-success" : "text-warning"}`}>{clean ? <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> : <AlertTriangle className="h-4 w-4" aria-hidden="true" />}{clean ? "Загружено" : `${warnings.toLocaleString("ru-RU")} предупреждений`}</span>;
}

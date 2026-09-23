"use client";
import Link from "next/link";
import { AuthGate } from "@/features/auth/auth-gate";
import { useLocalResearch } from "@/features/monitoring/local-research";
import ResearchAlertPage from "@/features/monitoring/research-alert-page";

export default function AlertPage({ params }: { params: Promise<{ id: string }> }) {
  if (useLocalResearch()) return <ResearchAlertPage params={params} />;
  // Historical source aliases are not canonical hospital or persisted Signal IDs.
  return <AuthGate><section className="mx-auto max-w-3xl space-y-4 rounded-xl border p-6">
    <h1 className="text-2xl font-semibold">Исследовательская карточка недоступна</h1>
    <p>Исторические карточки доступны только в локальном исследовательском режиме. Для работы с сохранёнными сигналами используйте защищённый список.</p>
    <div className="flex gap-4"><Link className="text-teal-700 underline" href="/signals">Открыть сигналы</Link><Link className="text-teal-700 underline" href="/monitor">К мониторингу</Link></div>
  </section></AuthGate>;
}

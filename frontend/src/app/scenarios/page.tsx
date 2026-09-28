"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AuthGate } from "@/features/auth/auth-gate";
import { ScenarioWorkbench } from "@/features/scenarios/components/scenario-workbench";

export default function ScenariosPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Загрузка…</p>}>
      <ScenariosContent />
    </Suspense>
  );
}

function ScenariosContent() {
  const search = useSearchParams();
  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-medium text-primary">MedSignal</p>
        <h1 className="mt-1 text-2xl font-semibold">Расчётный сценарий</h1>
        <p className="mt-1 text-sm text-muted-foreground">Прозрачное сравнение подтверждённого baseline с выбранным гипотетическим изменением потока.</p>
      </div>
      <AuthGate>
        <ScenarioWorkbench sourceSignalId={search.get("signal_id") ?? undefined} initialForecastId={search.get("forecast_id") ?? undefined} />
      </AuthGate>
    </div>
  );
}

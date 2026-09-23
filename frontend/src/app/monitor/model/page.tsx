"use client";
import { Suspense } from "react";
import { AuthGate } from "@/features/auth/auth-gate";
import { useSearchParams } from "next/navigation";
import { useLocalResearch } from "@/features/monitoring/local-research";
import { forecastLoginReturnTo } from "@/features/monitoring/forecast-login-return";
import { MonitorPage } from "@/features/monitoring/monitor-page";
import ResearchModelPage from "@/features/monitoring/research-model-page";

function ModelEvidenceRoute() {
  const forecastId = useSearchParams().get("forecast_id") ?? undefined;
  const research = useLocalResearch();
  return research && forecastId === undefined ? <ResearchModelPage /> : <MonitorPage forecastId={forecastId} />;
}

export default function ModelPage() {
  const research = useLocalResearch();
  const evidence = <Suspense fallback={<p role="status">Загрузка страницы прогноза…</p>}><ModelEvidenceRoute /></Suspense>;
  return research ? evidence : <AuthGate returnTo={() => forecastLoginReturnTo(new URLSearchParams(window.location.search).get("forecast_id") ?? undefined)}>{evidence}</AuthGate>;
}

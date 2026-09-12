"use client";

import { AuthGate } from "@/features/auth/auth-gate";
import { useAuth } from "@/features/auth/auth-context";
import { useHospitals } from "@/hooks/use-domain";

export default function HospitalsPage() {
  const { isAuthenticated } = useAuth();
  const hospitals = useHospitals(isAuthenticated);

  return (
    <div className="space-y-6">
      <section className="space-y-1.5">
        <h1 className="text-xl font-semibold tracking-tight">
          Медицинские организации
        </h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Показаны организации, доступные вашей учётной записи.
        </p>
      </section>

      <AuthGate>
        {hospitals.isPending && (
          <p className="text-sm text-muted-foreground">Загрузка…</p>
        )}
        {hospitals.isError && (
          <p className="text-sm text-destructive">
            Недоступно: {hospitals.error.message}
          </p>
        )}
        {hospitals.data && hospitals.data.items.length === 0 && (
          <p className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
            Доступных организаций нет. Возможно, область данных ещё
            не настроена администратором.
          </p>
        )}
        {hospitals.data && hospitals.data.items.length > 0 && (
          <ul className="divide-y divide-border rounded-lg border border-border bg-card">
            {hospitals.data.items.map((hospital) => (
              <li
                key={hospital.id}
                className="flex items-center justify-between px-4 py-3"
              >
                <span className="text-sm font-medium">{hospital.name}</span>
                <span className="text-xs text-muted-foreground">
                  {hospital.code}
                </span>
              </li>
            ))}
          </ul>
        )}
      </AuthGate>
    </div>
  );
}

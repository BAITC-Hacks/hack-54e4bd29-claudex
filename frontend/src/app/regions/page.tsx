"use client";

import { AuthGate } from "@/features/auth/auth-gate";
import { useAuth } from "@/features/auth/auth-context";
import { useRegions } from "@/hooks/use-domain";

export default function RegionsPage() {
  const { isAuthenticated } = useAuth();
  const regions = useRegions(isAuthenticated);

  return (
    <div className="space-y-6">
      <section className="space-y-1.5">
        <h1 className="text-xl font-semibold tracking-tight">Регионы</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Перечень ограничен областью данных учётной записи. Роли
          медицинской организации регионы не видят.
        </p>
      </section>

      <AuthGate>
        {regions.isPending && (
          <p className="text-sm text-muted-foreground">Загрузка…</p>
        )}
        {regions.isError && (
          <p className="text-sm text-destructive">
            Недоступно: {regions.error.message}
          </p>
        )}
        {regions.data && regions.data.items.length === 0 && (
          <p className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
            Доступных регионов нет.
          </p>
        )}
        {regions.data && regions.data.items.length > 0 && (
          <ul className="divide-y divide-border rounded-lg border border-border bg-card">
            {regions.data.items.map((region) => (
              <li
                key={region.id}
                className="flex items-center justify-between px-4 py-3"
              >
                <span className="text-sm font-medium">{region.name}</span>
                <span className="text-xs text-muted-foreground">
                  {region.code}
                </span>
              </li>
            ))}
          </ul>
        )}
      </AuthGate>
    </div>
  );
}

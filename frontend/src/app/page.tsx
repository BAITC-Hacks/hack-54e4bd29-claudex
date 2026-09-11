import { SystemStatusPanel } from "@/features/system-status/system-status-panel";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <section className="space-y-1.5">
        <h1 className="text-xl font-semibold tracking-tight">
          Состояние системы
        </h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Фундамент проекта: приложение, хранилища, очередь задач
          и аутентификация. Прикладные разделы — регионы, медицинские
          организации, сигналы и прогнозы — появляются в следующих этапах.
        </p>
      </section>

      <SystemStatusPanel />
    </div>
  );
}

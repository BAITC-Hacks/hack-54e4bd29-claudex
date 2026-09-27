"use client";

import {
  Activity,
  ArrowRight,
  BarChart3,
  BellRing,
  CheckCircle2,
  LineChart,
  LockKeyhole,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-context";

const capabilities = [
  {
    icon: BarChart3,
    title: "Единая аналитика",
    text: "Сводные показатели направлений, ожидания и отказов в одном рабочем контуре.",
  },
  {
    icon: BellRing,
    title: "Раннее выявление рисков",
    text: "Правила фиксируют измеримые отклонения и сохраняют подтверждающие факты.",
  },
  {
    icon: LineChart,
    title: "Прогнозирование",
    text: "Краткосрочный прогноз потока направлений с моделью, периодом валидации и метриками качества.",
  },
  {
    icon: ShieldCheck,
    title: "Поддержка решений",
    text: "Специалист получает контекст для проверки ситуации и сохраняет контроль над итоговым решением.",
  },
];

export function LandingPage() {
  const { isAuthenticated, login } = useAuth();

  return (
    <div className="overflow-hidden">
      <section className="border-b border-slate-200 bg-[#f5f8fa]">
        <div className="mx-auto grid w-full max-w-[1480px] gap-12 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-[minmax(0,0.92fr)_minmax(520px,1.08fr)] lg:items-center lg:px-8 lg:py-24">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-cyan-200 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.15em] text-cyan-900 shadow-sm">
              <Activity className="h-3.5 w-3.5" aria-hidden="true" /> Данные здравоохранения · Аналитика · Решения
            </p>
            <h1 className="mt-6 max-w-3xl text-4xl font-extrabold leading-[1.06] tracking-[-0.055em] text-[#102f45] sm:text-5xl lg:text-[58px]">
              Ситуационный центр здравоохранения
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg sm:leading-8">
              Мониторинг потоков направлений, выявление отклонений, прогнозирование нагрузки и поддержка решений на основе доступных данных.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              {isAuthenticated ? (
                <Link
                  href="/command-center"
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-[#087b83] px-5 text-sm font-bold text-white shadow-[0_10px_24px_-14px_rgba(8,123,131,.8)] transition hover:bg-[#066a71] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700 focus-visible:ring-offset-2"
                >
                  Открыть ситуационный центр <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              ) : (
                <Button type="button" className="h-12 px-5 text-sm shadow-[0_10px_24px_-14px_rgba(8,123,131,.8)]" onClick={() => void login()}>
                  <LockKeyhole className="h-4 w-4" aria-hidden="true" /> Войти в систему
                </Button>
              )}
              <a
                href="#capabilities"
                className="inline-flex h-12 items-center justify-center rounded-xl border border-slate-300 bg-white px-5 text-sm font-bold text-slate-700 transition hover:border-cyan-300 hover:text-cyan-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700"
              >
                Узнать больше
              </a>
            </div>
            <div className="mt-8 flex items-start gap-3 text-sm leading-6 text-slate-500">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-cyan-700" aria-hidden="true" />
              <p>Защищённые разделы доступны только авторизованным сотрудникам. Права доступа проверяет сервер.</p>
            </div>
          </div>

          <DashboardPreview />
        </div>
      </section>

      <section id="capabilities" className="bg-white py-16 sm:py-20">
        <div className="mx-auto w-full max-w-[1480px] px-4 sm:px-6 lg:px-8">
          <div className="max-w-2xl">
            <p className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-cyan-700">Возможности платформы</p>
            <h2 className="mt-3 text-3xl font-extrabold tracking-[-0.04em] text-[#102f45]">От данных к проверяемому действию</h2>
            <p className="mt-4 text-base leading-7 text-slate-600">Интерфейс помогает быстро увидеть ситуацию, проверить источник показателя и перейти к работе с сигналом.</p>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {capabilities.map((capability) => {
              const Icon = capability.icon;
              return (
                <article key={capability.title} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_16px_36px_-30px_rgba(15,46,68,.5)]">
                  <span className="grid h-11 w-11 place-items-center rounded-xl border border-cyan-100 bg-cyan-50 text-cyan-800"><Icon className="h-5 w-5" aria-hidden="true" /></span>
                  <h3 className="mt-5 text-base font-extrabold tracking-[-0.02em] text-[#102f45]">{capability.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{capability.text}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="border-y border-slate-200 bg-[#eef5f6] py-14 sm:py-16">
        <div className="mx-auto grid w-full max-w-[1480px] gap-8 px-4 sm:px-6 md:grid-cols-[1fr_auto] md:items-center lg:px-8">
          <div className="max-w-3xl">
            <p className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-cyan-800">Ответственное использование</p>
            <h2 className="mt-3 text-2xl font-extrabold tracking-[-0.035em] text-[#102f45]">Исследовательская демонстрационная среда</h2>
            <p className="mt-3 text-sm leading-7 text-slate-600">
              MedSignal — система поддержки решений. Она показывает доступные агрегаты, прогнозы и сигналы, но не принимает медицинские решения автономно. Итоговые действия определяет уполномоченный специалист.
            </p>
          </div>
          <div className="flex items-center gap-3 rounded-2xl border border-cyan-200 bg-white px-5 py-4 text-sm font-bold text-cyan-950 shadow-sm">
            <CheckCircle2 className="h-5 w-5 text-emerald-600" aria-hidden="true" /> Ограничения видны в интерфейсе
          </div>
        </div>
      </section>
    </div>
  );
}

function DashboardPreview() {
  return (
    <div className="relative mx-auto w-full max-w-[720px]" aria-label="Предварительный вид защищённого ситуационного центра">
      <div className="absolute -inset-5 -z-10 rounded-[36px] bg-cyan-100/60 blur-2xl" />
      <div className="overflow-hidden rounded-[24px] border border-slate-200 bg-white shadow-[0_28px_70px_-38px_rgba(15,46,68,.45)]">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <p className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-cyan-800">Ситуационный центр</p>
            <p className="mt-1 text-sm font-extrabold text-[#102f45]">Обзор системы</p>
          </div>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[9px] font-bold text-slate-500">Защищённый контур</span>
        </div>
        <div className="p-4 sm:p-5">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Направления", "text-cyan-700"],
              ["Ожидающие", "text-amber-700"],
              ["Отказы", "text-red-700"],
              ["Активные сигналы", "text-blue-700"],
            ].map(([label, tone]) => (
              <div key={label} className="rounded-xl border border-slate-200 bg-[#fbfdfd] p-3">
                <p className="text-[8px] font-bold uppercase tracking-[0.08em] text-slate-500">{label}</p>
                <p className={`mt-2 text-xl font-extrabold ${tone}`} aria-hidden="true">—</p>
              </div>
            ))}
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-[1.45fr_.75fr]">
            <div className="rounded-xl border border-slate-200 p-4">
              <div className="flex items-center justify-between"><p className="text-[10px] font-bold text-slate-700">Динамика направлений</p><span className="text-[8px] text-slate-400">Выбранный период</span></div>
              <svg className="mt-5 h-28 w-full" viewBox="0 0 420 110" role="img" aria-label="Схема графика без демонстрационных значений">
                <path d="M0 91H420M0 57H420M0 23H420" stroke="#e2e8f0" strokeWidth="1" />
                <path d="M4 83 C48 76 58 62 96 67 S154 82 191 55 S244 31 280 48 S337 68 416 20" fill="none" stroke="#087b83" strokeLinecap="round" strokeWidth="4" />
                <path d="M4 83 C48 76 58 62 96 67 S154 82 191 55 S244 31 280 48 S337 68 416 20 L416 106 L4 106 Z" fill="#dff4f2" opacity="0.8" />
              </svg>
            </div>
            <div className="rounded-xl border border-slate-200 p-4">
              <p className="text-[10px] font-bold text-slate-700">Последние сигналы</p>
              <div className="mt-4 space-y-3">
                {["Критический", "Предупреждение", "Информация"].map((label, index) => (
                  <div key={label} className="flex items-center gap-2.5">
                    <span className={`h-2.5 w-2.5 rounded-full ${index === 0 ? "bg-red-500" : index === 1 ? "bg-amber-400" : "bg-blue-500"}`} />
                    <span className="h-2 flex-1 rounded-full bg-slate-100" aria-label={label} />
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 rounded-xl border border-dashed border-cyan-200 bg-cyan-50/60 px-4 py-3 text-[10px] font-bold text-cyan-950">
            <LockKeyhole className="h-4 w-4" aria-hidden="true" /> Данные доступны после входа
          </div>
        </div>
      </div>
    </div>
  );
}

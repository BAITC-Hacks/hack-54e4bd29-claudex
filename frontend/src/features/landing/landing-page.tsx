"use client";

import { Activity, ArrowRight, BarChart3, BellRing, Building2, LineChart, LockKeyhole, ShieldCheck, Target, Users } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-context";

const capabilities = [
  { icon: BarChart3, title: "Актуальная аналитика", text: "Направления, ожидание и отказы в одной картине." },
  { icon: Target, title: "Раннее выявление", text: "Сигналы об измеримых отклонениях с проверяемыми фактами." },
  { icon: Users, title: "Поддержка решений", text: "Общий контекст по регионам и организациям для специалиста." },
];

export function LandingPage() {
  const { isAuthenticated, login } = useAuth();

  return (
    <div className="bg-[#f4f8fa] px-3 py-3 sm:px-5 sm:py-5 lg:px-7">
      <section className="mx-auto max-w-[1480px] overflow-hidden rounded-[24px] border border-white bg-[linear-gradient(135deg,#f7fbfc_0%,#edf6f8_62%,#e9f2f5_100%)] shadow-[0_30px_80px_-56px_rgba(15,46,68,.48)]">
        <div className="grid min-h-[620px] lg:grid-cols-[minmax(370px,.78fr)_minmax(560px,1.22fr)]">
          <div className="flex flex-col justify-between px-6 py-10 sm:px-10 lg:px-12 lg:py-14">
            <div>
              <p className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-cyan-700">Данные · аналитика · лидерство</p>
              <h1 className="mt-5 max-w-[620px] text-4xl font-extrabold leading-[1.04] tracking-[-0.055em] text-[#102f45] sm:text-5xl lg:text-[58px]">Ситуационный центр здравоохранения</h1>
              <p className="mt-6 max-w-[570px] text-base leading-7 text-slate-600 sm:text-lg sm:leading-8">Мониторинг потоков направлений, выявление отклонений и поддержка управленческих решений на основе доступных данных.</p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                {isAuthenticated ? (
                  <Link href="/command-center" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-[#078b94] px-6 text-sm font-extrabold text-white shadow-[0_14px_30px_-18px_rgba(7,139,148,.9)] transition hover:bg-[#067780]">Открыть центр <ArrowRight className="h-4 w-4" aria-hidden="true" /></Link>
                ) : (
                  <Button type="button" className="h-12 gap-2 px-6 text-sm font-extrabold" onClick={() => void login()}><ShieldCheck className="h-4 w-4" aria-hidden="true" /> Войти в систему <ArrowRight className="h-4 w-4" aria-hidden="true" /></Button>
                )}
                <a href="#capabilities" className="inline-flex h-12 items-center justify-center rounded-xl border-2 border-cyan-700/35 bg-white/70 px-6 text-sm font-extrabold text-cyan-900 transition hover:border-cyan-600 hover:bg-white">Узнать больше</a>
              </div>
            </div>
            <p className="mt-10 flex max-w-[570px] items-start gap-3 border-t border-slate-200/80 pt-5 text-xs leading-5 text-slate-500"><LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-cyan-700" aria-hidden="true" />MedSignal — система поддержки решений. Она не принимает медицинские решения автономно; итоговое действие определяет уполномоченный специалист.</p>
          </div>

          <HeroPreview />
        </div>

        <div id="capabilities" className="grid border-t border-white/90 bg-white/75 sm:grid-cols-3">
          {capabilities.map((item, index) => {
            const Icon = item.icon;
            return <article key={item.title} className={`flex gap-4 px-6 py-6 sm:px-8 ${index > 0 ? "border-t border-slate-200 sm:border-l sm:border-t-0" : ""}`}><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-cyan-50 text-cyan-700"><Icon className="h-5 w-5" aria-hidden="true" /></span><div><h2 className="text-sm font-extrabold text-[#12334a]">{item.title}</h2><p className="mt-1 text-xs leading-5 text-slate-500">{item.text}</p></div></article>;
          })}
        </div>
      </section>
    </div>
  );
}

function HeroPreview() {
  return (
    <div className="relative min-h-[560px] overflow-hidden border-t border-white/80 lg:min-h-0 lg:border-l lg:border-t-0" aria-label="Предварительный вид защищённого ситуационного центра">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_32%,rgba(78,201,204,.18),transparent_38%),linear-gradient(135deg,rgba(236,248,249,.92),rgba(218,237,241,.72))]" />
      <div className="absolute bottom-0 right-0 top-0 w-[32%] min-w-[190px] overflow-hidden">
        <Image src="/brand/astana-expo.jpg" alt="Современная архитектура Астаны" fill sizes="(min-width: 1024px) 24vw, 32vw" className="object-cover object-[57%_center]" priority />
        <div className="absolute inset-0 bg-gradient-to-b from-[#08394a]/5 via-transparent to-[#063b50]/80" />
        <p className="absolute bottom-8 left-5 right-5 text-lg font-extrabold leading-6 text-white">Здоровые регионы — сильнее страна</p>
      </div>
      <div className="relative z-10 mr-[27%] h-full px-5 py-8 sm:px-7 sm:py-10">
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <PreviewMetric icon={Activity} label="Направления" tone="text-cyan-700" />
          <PreviewMetric icon={Building2} label="Ожидающие" tone="text-amber-700" />
          <PreviewMetric icon={LineChart} label="Отказы" tone="text-rose-700" />
          <PreviewMetric icon={BellRing} label="Сигналы" tone="text-blue-700" />
        </div>
        <div className="relative mt-5 min-h-[330px]">
          <KazakhstanMap />
          <div className="absolute left-[20%] top-[34%] w-[175px] rounded-xl border border-white/90 bg-white/95 p-3 shadow-[0_18px_38px_-20px_rgba(15,46,68,.45)]"><p className="flex items-center gap-2 text-xs font-extrabold text-[#17364d]"><Building2 className="h-3.5 w-3.5" aria-hidden="true" /> Выбранный регион</p><p className="mt-2 text-[10px] text-slate-500">Показатели доступны после входа</p></div>
          <div className="absolute bottom-1 right-0 w-[48%] min-w-[210px] rounded-2xl border border-white/90 bg-white/95 p-4 shadow-[0_22px_50px_-28px_rgba(15,46,68,.5)]">
            <p className="text-[10px] font-extrabold text-[#17364d]">Динамика направлений</p>
            <svg className="mt-3 h-20 w-full" viewBox="0 0 260 82" role="img" aria-label="Схема графика без открытых значений"><path d="M0 67H260M0 41H260M0 15H260" stroke="#e2e8f0" /><path d="M3 64C28 51 42 56 62 42S102 58 125 40s35 1 55-12 34 2 76-23" fill="none" stroke="#07949d" strokeLinecap="round" strokeWidth="3.5" /></svg>
            <div className="mt-3 border-t border-slate-100 pt-3"><p className="text-[9px] font-extrabold uppercase tracking-wider text-slate-500">Последние сигналы</p><div className="mt-2 space-y-2"><SignalRow tone="bg-red-500" /><SignalRow tone="bg-amber-400" /><SignalRow tone="bg-blue-500" /></div></div>
          </div>
        </div>
        <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-cyan-100 bg-white/90 px-3 py-2 text-[10px] font-bold text-cyan-900 shadow-sm"><LockKeyhole className="h-3.5 w-3.5" aria-hidden="true" /> Данные доступны после входа</div>
      </div>
    </div>
  );
}

function PreviewMetric({ icon: Icon, label, tone }: { icon: typeof Activity; label: string; tone: string }) {
  return <div className="rounded-xl border border-white/90 bg-white/95 p-3 shadow-[0_14px_30px_-24px_rgba(15,46,68,.45)]"><Icon className={`h-4 w-4 ${tone}`} aria-hidden="true" /><p className="mt-3 text-[9px] font-bold uppercase tracking-wide text-slate-500">{label}</p><p className={`mt-1 text-xl font-extrabold ${tone}`} aria-hidden="true">—</p></div>;
}

function SignalRow({ tone }: { tone: string }) {
  return <div className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${tone}`} /><span className="h-1.5 flex-1 rounded-full bg-slate-100" /></div>;
}

function KazakhstanMap() {
  return <svg className="absolute left-0 top-12 h-[235px] w-[66%] text-cyan-400/30" viewBox="0 0 420 250" role="img" aria-label="Схематичная карта Казахстана без показателей"><path d="M25 98 61 72l42 2 30-31 47 10 33-21 40 24 47-4 22 28 55 8 18 31-25 22 7 34-46 4-22 24-49-6-31 24-42-19-44 7-25-31-51-11 10-30-31-18Z" fill="currentColor" stroke="#79cdd2" strokeWidth="2" /><path d="M112 76v102M196 53l-9 142M281 58l-12 127M55 119l309 25" fill="none" stroke="#f3fbfb" strokeWidth="2" opacity=".9" /><circle cx="178" cy="130" r="5" fill="#ef5968" stroke="white" strokeWidth="3" /></svg>;
}

"use client";

import {
  Activity,
  BarChart3,
  Building2,
  ChevronRight,
  FlaskConical,
  LogOut,
  MapPinned,
  Menu,
  Network,
  PanelLeftClose,
  RadioTower,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";
import { DECISION_SUPPORT_NOTICE, env } from "@/config/env";
import { useAuth } from "@/features/auth/auth-context";
import { cn } from "@/utils/cn";
import { SiteHeader } from "@/components/site-header";

interface NavigationItem {
  href: string;
  label: string;
  icon: typeof Activity;
}

const navigationGroups: Array<{ label: string; items: NavigationItem[] }> = [
  {
    label: "Ситуационный центр",
    items: [
      { href: "/command-center", label: "Обзор", icon: MapPinned },
      { href: "/dashboard", label: "Аналитика", icon: BarChart3 },
      { href: "/signals", label: "Сигналы", icon: RadioTower },
      { href: "/monitor", label: "Прогнозы", icon: Activity },
    ],
  },
  {
    label: "Организации",
    items: [
      { href: "/hospitals", label: "Организации", icon: Building2 },
      { href: "/regions", label: "Регионы и очередь", icon: Network },
    ],
  },
  {
    label: "Инструменты",
    items: [{ href: "/scenarios", label: "Сценарии", icon: FlaskConical }],
  },
];

const pageTitles: Record<string, string> = {
  "/command-center": "Ситуационный центр",
  "/dashboard": "Аналитика",
  "/signals": "Сигналы",
  "/monitor": "Прогнозы",
  "/hospitals": "Организации",
  "/regions": "Регионы и очередь",
  "/scenarios": "Сценарии",
};

function activeRoute(pathname: string): string | undefined {
  return navigationGroups
    .flatMap((group) => group.items)
    .filter((item) => pathname === item.href || pathname.startsWith(`${item.href}/`))
    .sort((first, second) => second.href.length - first.href.length)[0]?.href;
}

function AppNavigation({
  pathname,
  onNavigate,
  ariaLabel = "Основная навигация",
}: {
  pathname: string;
  onNavigate?: () => void;
  ariaLabel?: string;
}) {
  const active = activeRoute(pathname);
  return (
    <nav aria-label={ariaLabel} className="space-y-6">
      {navigationGroups.map((group) => (
        <div key={group.label}>
          <p className="mb-2 px-3 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-400">
            {group.label}
          </p>
          <div className="space-y-1">
            {group.items.map((item) => {
              const Icon = item.icon;
              const selected = item.href === active;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={selected ? "page" : undefined}
                  onClick={onNavigate}
                  className={cn(
                    "group flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700",
                    selected && "bg-cyan-50 text-cyan-950 shadow-[inset_3px_0_0_#087b83] hover:bg-cyan-50 hover:text-cyan-950",
                  )}
                >
                  <Icon className={cn("h-[18px] w-[18px] text-slate-400", selected && "text-cyan-700")} aria-hidden="true" />
                  <span className="flex-1">{item.label}</span>
                  {selected && <ChevronRight className="h-4 w-4 text-cyan-600" aria-hidden="true" />}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}

function AppBrand() {
  return (
    <Link
      href="/command-center"
      className="flex items-center gap-3 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700"
      aria-label="MedSignal — ситуационный центр"
    >
      <BrandMark compact className="text-[#087b83]" />
      <span className="leading-none">
        <span className="block text-[17px] font-extrabold tracking-[-0.045em] text-[#102f45]">MedSignal</span>
        <span className="mt-1 block text-[8px] font-bold uppercase tracking-[0.18em] text-slate-500">Decision support</span>
      </span>
    </Link>
  );
}

function AppFooter() {
  if (!env.disclaimerEnabled) return null;

  return (
    <footer className="border-t border-slate-200 bg-white px-4 py-4 sm:px-6 lg:px-8">
      <p className="mx-auto max-w-[1440px] text-[11px] leading-5 text-slate-500">{DECISION_SUPPORT_NOTICE}</p>
    </footer>
  );
}

export function ApplicationShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";

  // A route change remounts private drawer state, so browser navigation cannot
  // reopen a menu from the previous page and no synchronization effect is needed.
  return <ApplicationShellContent key={pathname} pathname={pathname}>{children}</ApplicationShellContent>;
}

function ApplicationShellContent({ children, pathname }: { children: ReactNode; pathname: string }) {
  const { isAuthenticated, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const isPublicRoute = pathname === "/" || pathname.startsWith("/auth/");

  useEffect(() => {
    if (mobileOpen) closeButton.current?.focus();
  }, [mobileOpen]);

  function closeMobileNavigation(): void {
    setMobileOpen(false);
    menuButton.current?.focus();
  }

  if (!isAuthenticated || isPublicRoute) {
    return (
      <div className="flex min-h-screen flex-col">
        <SiteHeader />
        <main id="main-content" className={cn("flex-1", pathname === "/" ? "" : "mx-auto w-full max-w-[1480px] px-4 py-8 sm:px-6 lg:px-8")}>
          {children}
        </main>
        <AppFooter />
      </div>
    );
  }

  const title = Object.entries(pageTitles)
    .filter(([href]) => pathname === href || pathname.startsWith(`${href}/`))
    .sort(([first], [second]) => second.length - first.length)[0]?.[1] ?? "MedSignal";

  return (
    <div className="min-h-screen bg-[#f5f8fa] lg:flex">
      <aside className="sticky top-0 hidden h-screen w-[260px] shrink-0 flex-col border-r border-slate-200 bg-white px-4 py-5 lg:flex">
        <div className="px-2"><AppBrand /></div>
        <div className="mt-8 flex-1 overflow-y-auto pr-1"><AppNavigation pathname={pathname} /></div>
        <div className="mt-5 border-t border-slate-200 pt-4">
          <div className="mb-3 rounded-xl border border-cyan-100 bg-cyan-50/70 px-3 py-3">
            <p className="text-[10px] font-extrabold uppercase tracking-[0.12em] text-cyan-800">Демо-среда</p>
            <p className="mt-1 text-[11px] leading-4 text-slate-600">Исследовательский контур поддержки решений</p>
          </div>
          <Button type="button" variant="ghost" className="w-full justify-start text-slate-600" onClick={logout}>
            <LogOut className="h-4 w-4" aria-hidden="true" /> Выйти
          </Button>
        </div>
      </aside>

      <div className="flex min-h-screen min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-slate-200/90 bg-white/95 backdrop-blur">
          <div className="flex min-h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
            <button
              ref={menuButton}
              type="button"
              className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700 lg:hidden"
              aria-label="Открыть меню"
              aria-expanded={mobileOpen}
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="h-5 w-5" aria-hidden="true" />
            </button>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-extrabold tracking-[-0.02em] text-[#102f45]">{title}</p>
              <p className="hidden text-[11px] text-slate-500 sm:block">Защищённый аналитический контур</p>
            </div>
            <span className="hidden rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.1em] text-cyan-900 sm:inline-flex">Исследовательский пилот</span>
            <span className="grid h-9 w-9 place-items-center rounded-full bg-[#12334a] text-xs font-extrabold text-white" aria-label="Профиль пользователя">МС</span>
          </div>
        </header>

        <main id="main-content" className="mx-auto w-full max-w-[1540px] flex-1 px-4 py-5 sm:px-6 sm:py-7 lg:px-8 lg:py-8">
          {children}
        </main>
        <AppFooter />
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button className="absolute inset-0 bg-slate-950/40" aria-label="Закрыть меню" onClick={closeMobileNavigation} />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Навигация MedSignal"
            className="relative flex h-full w-[min(88vw,320px)] flex-col bg-white p-4 shadow-2xl"
            onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); closeMobileNavigation(); } }}
          >
            <div className="flex items-center justify-between gap-4 px-1 pb-5">
              <AppBrand />
              <button
                ref={closeButton}
                type="button"
                className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700"
                aria-label="Закрыть навигацию"
                onClick={closeMobileNavigation}
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto py-3">
              <AppNavigation
                pathname={pathname}
                onNavigate={closeMobileNavigation}
                ariaLabel="Мобильная навигация"
              />
            </div>
            <Button type="button" variant="ghost" className="mt-4 justify-start border-t border-slate-200 text-slate-600" onClick={logout}>
              <PanelLeftClose className="h-4 w-4" aria-hidden="true" /> Выйти
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

"use client";

import { LogIn, LogOut, Menu, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState, type KeyboardEvent } from "react";

import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";
import { env } from "@/config/env";
import { useAuth } from "@/features/auth/auth-context";
import { useLocalResearch } from "@/features/monitoring/local-research";
import { cn } from "@/utils/cn";

const navigation = (research: boolean) => research ? [
  { href: "/monitor", label: "Предупреждения" },
  { href: "/monitor/model", label: "Обучение" },
] : [
  { href: "/command-center", label: "Карта" },
  { href: "/monitor", label: "Мониторинг" },
  { href: "/dashboard", label: "Аналитика" },
  { href: "/signals", label: "Сигналы" },
  { href: "/scenarios", label: "Сценарии" },
  { href: "/hospitals", label: "Организации" },
  { href: "/regions", label: "Регионы" },
];

export function SiteHeader() {
  const pathname = usePathname();
  const research = useLocalResearch();

  // A route or mode change remounts the menu, so browser back cannot reopen it.
  return <SiteHeaderContent key={`${pathname}:${research}`} pathname={pathname} research={research} />;
}

function SiteHeaderContent({ pathname, research }: { pathname: string; research: boolean }) {
  const { isAuthenticated, login, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const items = navigation(research);
  const activeHref = items
    .filter((item) => pathname === item.href || (item.href !== "/command-center" && pathname.startsWith(`${item.href}/`)))
    .sort((first, second) => second.href.length - first.href.length)[0]?.href;

  function handleHeaderKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape" && menuOpen) {
      setMenuOpen(false);
      menuButton.current?.focus();
    }
  }

  return (
    <header className="sticky top-0 z-[1100] border-b border-slate-200/80 bg-[#f7fbfc]/90 backdrop-blur-xl" onKeyDown={handleHeaderKeyDown}>
      <div className="h-1 bg-[linear-gradient(90deg,#087d85_0%,#12a8ae_58%,#f0bd45_58%,#f0bd45_66%,#1e4b7a_66%)]" />
      <div className="container flex min-h-[68px] items-center justify-between gap-6 py-2">
        <div className="flex min-w-0 items-center gap-8">
          <Link href="/" className="group flex shrink-0 items-center gap-3" aria-label="MedFlow — главная">
            <BrandMark compact className="text-[#087d85] shadow-[0_8px_22px_-10px_rgba(8,125,133,.7)] transition-transform group-hover:-rotate-3 group-hover:scale-105" />
            <span className="leading-none">
              <span className="block text-[17px] font-extrabold tracking-[-0.055em] text-[#102f45]">MedFlow</span>
              <span className="mt-1 block text-[8px] font-extrabold uppercase tracking-[0.19em] text-cyan-700">Health intelligence</span>
            </span>
          </Link>

          <nav aria-label="Основная навигация" className="hidden items-center gap-1 rounded-xl border border-slate-200/80 bg-white/75 p-1 shadow-[0_8px_24px_-22px_rgba(15,46,68,.8)] lg:flex">
            {items.map((item) => {
              const active = item.href === activeHref;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "rounded-lg px-3 py-2 text-[11px] font-bold text-slate-500 transition-colors hover:bg-cyan-50 hover:text-cyan-800",
                    active && "bg-[#0d7f87] text-white shadow-sm hover:bg-[#0d7f87] hover:text-white",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button
            ref={menuButton}
            type="button"
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl border border-slate-200 bg-white text-cyan-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700 lg:hidden"
            aria-label={menuOpen ? "Закрыть меню" : "Открыть меню"}
            aria-controls="mobile-site-navigation"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
          </button>
          <span className="hidden items-center gap-1.5 rounded-full border border-cyan-100 bg-cyan-50/70 px-2.5 py-1.5 text-[9px] font-extrabold uppercase tracking-[.1em] text-cyan-800 sm:flex">
            <ShieldCheck size={12} /> Минздрав РК
          </span>
          <span className="hidden rounded-full bg-slate-100 px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-slate-500 xl:block">{env.appEnv}</span>
          {research ? (
            <span className="text-xs font-semibold text-amber-700">Локальный пилот</span>
          ) : isAuthenticated ? (
            <Button className="gap-2" size="sm" variant="ghost" onClick={logout}>
              <LogOut size={14} /> Выйти
            </Button>
          ) : (
            <Button className="gap-2 rounded-xl border-cyan-700 bg-white text-cyan-800 hover:bg-cyan-50" size="sm" variant="outline" onClick={() => void login()}>
              <LogIn size={14} /> Войти
            </Button>
          )}
        </div>
      </div>
      {menuOpen && (
        <nav id="mobile-site-navigation" aria-label="Мобильная навигация" className="container grid gap-1 border-t border-slate-200/80 pb-3 pt-2 lg:hidden">
          {items.map((item) => {
            const active = item.href === activeHref;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                onClick={() => setMenuOpen(false)}
                className={cn(
                  "rounded-lg px-3 py-3 text-sm font-semibold text-slate-700 transition-colors hover:bg-cyan-50 hover:text-cyan-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700",
                  active && "bg-[#0d7f87] text-white hover:bg-[#0d7f87] hover:text-white",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      )}
    </header>
  );
}

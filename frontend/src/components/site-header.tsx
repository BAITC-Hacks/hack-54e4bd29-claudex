"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { env } from "@/config/env";
import { useAuth } from "@/features/auth/auth-context";
import { cn } from "@/utils/cn";

const NAVIGATION = process.env.NEXT_PUBLIC_PILOT_MODE === "true" ? [
  {href: "/monitor", label: "Предупреждения"},
  {href: "/monitor/model", label: "Обучение и проверка"},
] : [
  { href: "/command-center", label: "Карта Казахстана" },
  { href: "/dashboard", label: "Ситуационный центр" },
  { href: "/signals", label: "Сигналы" },
  { href: "/scenarios", label: "Сценарии" },
  { href: "/hospitals", label: "Организации" },
  { href: "/regions", label: "Регионы" },
];

export function SiteHeader() {
  const pathname = usePathname();
  const { isAuthenticated, login, logout } = useAuth();

  return (
    <header className="border-b border-border bg-card">
      <div className="container flex h-14 items-center justify-between gap-6">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2 text-sm font-semibold tracking-tight">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-teal-700 text-xs font-bold text-white shadow-sm">M</span>
            <span>MedFlow <em className="not-italic text-teal-700">AI</em></span>
          </Link>
          <nav className="flex items-center gap-4">
            {NAVIGATION.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "text-sm text-muted-foreground hover:text-foreground",
                  pathname === item.href && "font-medium text-foreground",
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">{env.appEnv}</span>
          {process.env.NEXT_PUBLIC_PILOT_MODE === "true" ? <span className="text-xs font-medium text-amber-700">Локальный пилот</span> : isAuthenticated ? (
            <Button size="sm" variant="ghost" onClick={logout}>
              Выйти
            </Button>
          ) : (
            <Button size="sm" variant="outline" onClick={() => void login()}>
              Войти
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { env } from "@/config/env";
import { useAuth } from "@/features/auth/auth-context";
import { cn } from "@/utils/cn";

const NAVIGATION = [
  { href: "/", label: "Состояние" },
  { href: "/signals", label: "Сигналы" },
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
          <Link href="/" className="text-sm font-semibold tracking-tight">
            MedSignal
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
          {isAuthenticated ? (
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

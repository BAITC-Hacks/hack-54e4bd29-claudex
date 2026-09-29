"use client";

import { ArrowRight, LogIn, LogOut } from "lucide-react";
import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-context";
import { LogoutButton } from "@/features/auth/logout-button";
import { useLocalResearch } from "@/features/monitoring/local-research";

export function SiteHeader() {
  const { isAuthenticated, login } = useAuth();
  const research = useLocalResearch();

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/90 bg-white/95 backdrop-blur">
      <div className="mx-auto flex min-h-16 w-full max-w-[1480px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Link
          href="/"
          className="group flex shrink-0 items-center gap-3 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700 focus-visible:ring-offset-4"
          aria-label="MedSignal — главная"
        >
          <BrandMark compact className="text-[#087b83]" />
          <span className="leading-none">
            <span className="block text-[17px] font-extrabold tracking-[-0.045em] text-[#102f45]">MedSignal</span>
            <span className="mt-1 block text-[8px] font-bold uppercase tracking-[0.18em] text-slate-500">Healthcare analytics</span>
          </span>
        </Link>

        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <span className="hidden rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.11em] text-cyan-900 sm:inline-flex">
            {research ? "Локальный пилот" : "Исследовательский пилот"}
          </span>
          {isAuthenticated ? (
            <>
              <Link
                href="/command-center"
                className="inline-flex h-9 items-center gap-2 rounded-xl bg-[#087b83] px-3.5 text-xs font-bold text-white transition hover:bg-[#066a71] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700 focus-visible:ring-offset-2"
              >
                Открыть центр <ArrowRight size={14} aria-hidden="true" />
              </Link>
              <LogoutButton size="sm" variant="ghost" aria-label="Выйти">
                <LogOut size={15} aria-hidden="true" />
                <span className="hidden sm:inline">Выйти</span>
              </LogoutButton>
            </>
          ) : (
            <Button
              type="button"
              className="h-9 border-cyan-700 bg-white px-3.5 text-cyan-900 hover:bg-cyan-50"
              size="sm"
              variant="outline"
              onClick={() => void login()}
            >
              <LogIn size={15} aria-hidden="true" /> Войти
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}

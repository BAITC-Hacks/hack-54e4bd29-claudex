import type { Metadata } from "next";

import { Providers } from "@/app/providers";
import { SiteHeader } from "@/components/site-header";
import { DECISION_SUPPORT_NOTICE, env } from "@/config/env";

import "@/app/globals.css";

export const metadata: Metadata = {
  title: "MedFlow AI | Минздрав РК",
  description:
    "Система раннего предупреждения о риске перегрузки медицинских организаций",
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body className="min-h-screen">
        <Providers>
          <div className="flex min-h-screen flex-col">
            <SiteHeader />

            <main className="container flex-1 py-7 lg:py-10">{children}</main>

            {env.disclaimerEnabled && (
              <footer className="border-t border-slate-200/80 bg-white/70 backdrop-blur">
                <div className="container flex items-center justify-between gap-5 py-5">
                  <p className="max-w-4xl text-[11px] leading-5 text-slate-500">
                    {DECISION_SUPPORT_NOTICE}
                  </p>
                  <span className="hidden text-[10px] font-bold uppercase tracking-[0.16em] text-cyan-700 md:block">MedFlow · 2026</span>
                </div>
              </footer>
            )}
          </div>
        </Providers>
      </body>
    </html>
  );
}

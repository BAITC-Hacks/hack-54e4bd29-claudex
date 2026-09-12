import type { Metadata } from "next";

import { Providers } from "@/app/providers";
import { SiteHeader } from "@/components/site-header";
import { DECISION_SUPPORT_NOTICE, env } from "@/config/env";

import "@/app/globals.css";

export const metadata: Metadata = {
  title: "MedSignal",
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

            <main className="container flex-1 py-8">{children}</main>

            {env.disclaimerEnabled && (
              <footer className="border-t border-border bg-card">
                <div className="container py-4">
                  <p className="text-xs text-muted-foreground">
                    {DECISION_SUPPORT_NOTICE}
                  </p>
                </div>
              </footer>
            )}
          </div>
        </Providers>
      </body>
    </html>
  );
}

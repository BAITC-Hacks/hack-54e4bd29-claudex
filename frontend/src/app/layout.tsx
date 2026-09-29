import type { Metadata } from "next";

import { Providers } from "@/app/providers";
import { ApplicationShell } from "@/components/application-shell";

import "@/app/globals.css";

export const metadata: Metadata = {
  title: "MedSignal — исследовательский пилот",
  description:
    "Система раннего предупреждения о риске перегрузки медицинских организаций",
  icons: {
    icon: "/brand/medsignal-icon.png",
    apple: "/brand/medsignal-icon.png",
  },
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body className="min-h-screen">
        <Providers>
          <ApplicationShell>{children}</ApplicationShell>
        </Providers>
      </body>
    </html>
  );
}

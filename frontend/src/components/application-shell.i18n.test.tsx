import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";

import { ApplicationShell } from "@/components/application-shell";
import { LanguageProvider } from "@/features/i18n/i18n-context";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; children: ReactNode }) =>
    <a href={href} {...props}>{children}</a>,
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/command-center" }));
vi.mock("@/features/auth/auth-context", () => ({
  useAuth: () => ({ isAuthenticated: true, logout: vi.fn() }),
}));

beforeEach(() => window.localStorage.clear());

it("shows a readable Russian/Kazakh switch inside the protected situation center", async () => {
  render(<LanguageProvider><ApplicationShell><p>Protected content</p></ApplicationShell></LanguageProvider>);

  expect(screen.getByRole("button", { name: "Рус" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Қаз" }));
  await waitFor(() => expect(screen.getByRole("navigation", { name: "Негізгі навигация" })).toHaveTextContent("Шолу"));
  expect(screen.getByRole("button", { name: "Қаз" })).toHaveAttribute("aria-pressed", "true");
});

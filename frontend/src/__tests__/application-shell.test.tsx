import { fireEvent, render, screen, within } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApplicationShell } from "@/components/application-shell";

const state = vi.hoisted(() => ({ isAuthenticated: true, pathname: "/signals", disclaimerEnabled: true }));

vi.mock("next/navigation", () => ({ usePathname: () => state.pathname }));
vi.mock("next/link", () => ({
  default: ({ href, children, onClick, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; children: ReactNode }) =>
    <a href={href} onClick={(event) => { event.preventDefault(); onClick?.(event); }} {...props}>{children}</a>,
}));
vi.mock("@/features/monitoring/local-research", () => ({ useLocalResearch: () => false }));
vi.mock("@/features/auth/auth-context", () => ({
  useAuth: () => ({ isAuthenticated: state.isAuthenticated, login: vi.fn(), logout: vi.fn() }),
}));
vi.mock("@/config/env", () => ({
  DECISION_SUPPORT_NOTICE: "Решение принимает уполномоченный сотрудник.",
  env: { get disclaimerEnabled() { return state.disclaimerEnabled; } },
}));

afterEach(() => {
  state.isAuthenticated = true;
  state.pathname = "/signals";
  state.disclaimerEnabled = true;
});

describe("ApplicationShell", () => {
  it("shows authenticated navigation with only working product routes", () => {
    render(<ApplicationShell><p>Рабочая область</p></ApplicationShell>);

    const sidebar = screen.getByRole("navigation", { name: "Основная навигация" });
    expect(within(sidebar).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
      "/command-center", "/dashboard", "/signals", "/monitor", "/hospitals", "/regions", "/scenarios",
    ]);
    expect(within(sidebar).getByRole("link", { name: "Сигналы" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Рабочая область")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /отч[её]ты/i })).not.toBeInTheDocument();
  });

  it("uses an accessible mobile drawer that closes on Escape and returns focus", () => {
    render(<ApplicationShell><p>Рабочая область</p></ApplicationShell>);

    const toggle = screen.getByRole("button", { name: "Открыть меню" });
    fireEvent.click(toggle);
    const drawer = screen.getByRole("dialog", { name: "Навигация MedSignal" });
    expect(within(drawer).getByRole("navigation", { name: "Мобильная навигация" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Сигналы" })).toBeInTheDocument();

    fireEvent.keyDown(drawer, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Навигация MedSignal" })).not.toBeInTheDocument();
    expect(toggle).toHaveFocus();
  });

  it("does not render the application sidebar for unauthenticated routes", () => {
    state.isAuthenticated = false;
    render(<ApplicationShell><p>Публичная страница</p></ApplicationShell>);

    expect(screen.queryByRole("navigation", { name: "Основная навигация" })).not.toBeInTheDocument();
    expect(screen.getByText("Публичная страница")).toBeInTheDocument();
  });

  it("honors the existing disclaimer feature flag", () => {
    state.disclaimerEnabled = false;
    render(<ApplicationShell><p>Рабочая область</p></ApplicationShell>);

    expect(screen.queryByText("Решение принимает уполномоченный сотрудник.")).not.toBeInTheDocument();
  });
});

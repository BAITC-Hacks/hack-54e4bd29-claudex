import { fireEvent, render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SiteHeader } from "@/components/site-header";

const state = vi.hoisted(() => ({ isAuthenticated: false, research: false }));
const login = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; children: ReactNode }) =>
    <a href={href} {...props}>{children}</a>,
}));
vi.mock("@/features/monitoring/local-research", () => ({
  useLocalResearch: () => state.research,
}));
vi.mock("@/features/auth/auth-context", () => ({
  useAuth: () => ({ isAuthenticated: state.isAuthenticated, login, logout: vi.fn() }),
}));

afterEach(() => {
  state.isAuthenticated = false;
  state.research = false;
  login.mockReset();
});

describe("SiteHeader public navigation", () => {
  it("hides every protected route before authentication", () => {
    render(<SiteHeader />);

    expect(screen.getByRole("link", { name: "MedSignal — главная" })).toBeInTheDocument();
    expect(screen.getByText("Исследовательский пилот")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Войти" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: /навигация/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Сигналы" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Аналитика" })).not.toBeInTheDocument();
  });

  it("starts sign-in only after the user activates the button", () => {
    render(<SiteHeader />);

    expect(login).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Войти" }));
    expect(login).toHaveBeenCalledTimes(1);
  });
});

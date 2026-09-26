import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SiteHeader } from "@/components/site-header";

const state = vi.hoisted(() => ({ pathname: "/dashboard", research: false }));

vi.mock("next/navigation", () => ({ usePathname: () => state.pathname }));
vi.mock("next/link", () => ({
  default: ({ href, children, onClick, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; children: ReactNode }) =>
    <a href={href} onClick={(event) => { event.preventDefault(); onClick?.(event); }} {...props}>{children}</a>,
}));
vi.mock("@/features/monitoring/local-research", () => ({
  useLocalResearch: () => state.research,
}));
vi.mock("@/features/auth/auth-context", () => ({
  useAuth: () => ({ isAuthenticated: true, login: vi.fn(), logout: vi.fn() }),
}));

afterEach(() => {
  cleanup();
  state.pathname = "/dashboard";
  state.research = false;
});

describe("SiteHeader responsive navigation", () => {
  it("exposes every standard route in the compact menu and marks the active route", () => {
    render(<SiteHeader />);

    expect(screen.getByRole("link", { name: "MedSignal — главная" })).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Открыть меню" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation", { name: "Мобильная навигация" })).not.toBeInTheDocument();

    fireEvent.click(toggle);
    const menu = screen.getByRole("navigation", { name: "Мобильная навигация" });
    expect(screen.getByRole("button", { name: "Закрыть меню" })).toHaveAttribute("aria-expanded", "true");
    expect(within(menu).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
      "/command-center", "/monitor", "/dashboard", "/signals", "/scenarios", "/hospitals", "/regions",
    ]);
    expect(within(menu).getByRole("link", { name: "Аналитика" })).toHaveAttribute("aria-current", "page");
    const desktop = screen.getByRole("navigation", { name: "Основная навигация" });
    expect(within(desktop).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(
      within(menu).getAllByRole("link").map((link) => link.getAttribute("href")),
    );
  });

  it("closes on Escape, returns focus to the toggle, and closes after choosing a link", () => {
    render(<SiteHeader />);
    fireEvent.click(screen.getByRole("button", { name: "Открыть меню" }));
    const menu = screen.getByRole("navigation", { name: "Мобильная навигация" });
    within(menu).getByRole("link", { name: "Сигналы" }).focus();

    fireEvent.keyDown(menu, { key: "Escape" });
    expect(screen.queryByRole("navigation", { name: "Мобильная навигация" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Открыть меню" })).toHaveFocus();

    fireEvent.click(screen.getByRole("button", { name: "Открыть меню" }));
    fireEvent.click(within(screen.getByRole("navigation", { name: "Мобильная навигация" })).getByRole("link", { name: "Регионы" }));
    expect(screen.queryByRole("navigation", { name: "Мобильная навигация" })).not.toBeInTheDocument();
  });

  it("keeps research routes separate and closes when mode or route changes", () => {
    state.research = true;
    state.pathname = "/monitor/model";
    const view = render(<SiteHeader />);
    fireEvent.click(screen.getByRole("button", { name: "Открыть меню" }));
    const menu = screen.getByRole("navigation", { name: "Мобильная навигация" });
    expect(within(menu).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
      "/monitor", "/monitor/model",
    ]);
    expect(within(menu).getByRole("link", { name: "Обучение" })).toHaveAttribute("aria-current", "page");
    expect(within(menu).getByRole("link", { name: "Предупреждения" })).not.toHaveAttribute("aria-current");
    expect(within(menu).queryByRole("link", { name: "Сигналы" })).not.toBeInTheDocument();

    state.pathname = "/monitor";
    view.rerender(<SiteHeader />);
    expect(screen.queryByRole("navigation", { name: "Мобильная навигация" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Открыть меню" }));
    state.research = false;
    view.rerender(<SiteHeader />);
    expect(screen.queryByRole("navigation", { name: "Мобильная навигация" })).not.toBeInTheDocument();
  });
});

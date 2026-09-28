import { fireEvent, render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { expect, it, vi } from "vitest";

import { LandingPage } from "@/features/landing/landing-page";

const login = vi.hoisted(() => vi.fn());

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; children: ReactNode }) =>
    <a href={href} {...props}>{children}</a>,
}));
vi.mock("@/features/auth/auth-context", () => ({
  useAuth: () => ({ isAuthenticated: false, login }),
}));

it("explains the product, its limits, and the protected entry point without invented metrics", () => {
  render(<LandingPage />);

  expect(screen.getByRole("heading", { level: 1, name: "Ситуационный центр здравоохранения" })).toBeInTheDocument();
  expect(screen.getByText(/мониторинг потоков направлений/i)).toBeInTheDocument();
  expect(screen.getByText(/система поддержки решений/i)).toBeInTheDocument();
  expect(screen.getByText(/не принимает медицинские решения автономно/i)).toBeInTheDocument();
  expect(screen.getByText("Данные доступны после входа")).toBeInTheDocument();
  expect(screen.queryByText(/\b\d{3,}\b/)).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Войти в систему" }));
  expect(login).toHaveBeenCalledTimes(1);
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";

import { Providers } from "@/app/providers";
import { SiteHeader } from "@/components/site-header";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; children: ReactNode }) =>
    <a href={href} {...props}>{children}</a>,
}));

beforeEach(() => window.localStorage.clear());

it("switches the public header between Russian and Kazakh", async () => {
  render(<Providers><SiteHeader /></Providers>);

  expect(screen.getByText("Исследовательский пилот")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Қаз" }));
  await waitFor(() => expect(screen.getByText("Зерттеу пилоты")).toBeInTheDocument());
  expect(document.documentElement.lang).toBe("kk");

  fireEvent.click(screen.getByRole("button", { name: "Рус" }));
  await waitFor(() => expect(screen.getByText("Исследовательский пилот")).toBeInTheDocument());
  expect(document.documentElement.lang).toBe("ru");
});

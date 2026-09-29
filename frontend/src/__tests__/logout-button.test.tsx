import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LogoutButton } from "@/features/auth/logout-button";

vi.mock("@/features/auth/auth-context", () => ({
  useAuth: () => ({ logout: vi.fn() }),
}));

describe("LogoutButton", () => {
  it("renders the modal outside the trigger stacking context", () => {
    const { container } = render(<LogoutButton>Выйти</LogoutButton>);

    fireEvent.click(screen.getByRole("button", { name: "Выйти" }));

    expect(screen.getByRole("dialog", { name: "Выйти из MedSignal?" })).toBeInTheDocument();
    expect(within(container).queryByRole("dialog")).not.toBeInTheDocument();
  });
});

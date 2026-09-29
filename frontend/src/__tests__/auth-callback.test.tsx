import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AuthCallbackPage from "@/app/auth/callback/page";

const router = vi.hoisted(() => ({ replace: vi.fn() }));
const setToken = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

vi.mock("@/features/auth/auth-context", () => ({
  AUTH_CALLBACK_PATH: "/auth/callback",
  useAuth: () => ({ setToken }),
}));

beforeEach(() => {
  router.replace.mockReset();
  setToken.mockReset();
  sessionStorage.clear();
  sessionStorage.setItem("medsignal.pkce.verifier", "synthetic-verifier");
  sessionStorage.setItem("medsignal.pkce.state", "synthetic-state");
  sessionStorage.setItem("medsignal.pkce.return_to", "/dashboard?period=quarter");
  window.history.replaceState(null, "", "/auth/callback?code=synthetic-code&state=synthetic-state");
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
});

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("AuthCallbackPage", () => {
  it("hides the callback URL before the token exchange completes", async () => {
    render(<AuthCallbackPage />);

    await waitFor(() => {
      expect(`${window.location.pathname}${window.location.search}`).toBe(
        "/dashboard?period=quarter",
      );
    });
    expect(router.replace).not.toHaveBeenCalled();
  });
});

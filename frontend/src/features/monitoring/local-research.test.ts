import { execFileSync } from "node:child_process";
import { afterEach, describe, expect, it, vi } from "vitest";
import { pilotApi } from "./api";

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.resetModules(); });
const cases = [
  [undefined, "local", "development", false], ["false", "local", "development", false],
  ["TRUE", "local", "development", false], ["true", undefined, "development", false],
  ["true", "production", "development", false], ["true", "staging", "development", false],
  ["true", "dev", "development", false], ["true", "local", "production", false],
  ["true", "test", "production", false], ["true", "local", "development", true],
  ["true", "test", "test", true],
] as const;

describe("strict local research configuration", () => {
  it.each(cases)("flag %s, app %s, runtime %s => research %s", async (flag, app, runtime, enabled) => {
    vi.stubEnv("NEXT_PUBLIC_PILOT_MODE", flag); vi.stubEnv("NEXT_PUBLIC_APP_ENV", app); vi.stubEnv("NODE_ENV", runtime);
    vi.resetModules();
    const { env } = await import("@/config/env");
    expect(env).toHaveProperty("pilotModeEnabled", enabled);
  });
  it.each(cases)("does not expose the pilot proxy unless explicitly local: %s/%s/%s", (flag, app, runtime, enabled) => {
    const childEnv: NodeJS.ProcessEnv = { ...process.env, PILOT_API_URL: "http://pilot-api:8000", NODE_ENV: runtime };
    if (flag === undefined) delete childEnv.NEXT_PUBLIC_PILOT_MODE; else childEnv.NEXT_PUBLIC_PILOT_MODE = flag;
    if (app === undefined) delete childEnv.NEXT_PUBLIC_APP_ENV; else childEnv.NEXT_PUBLIC_APP_ENV = app;
    const result = execFileSync(process.execPath, ["--input-type=module", "-e", "import config from './next.config.mjs'; console.log(JSON.stringify(await config.rewrites()))"], { cwd: process.cwd(), env: childEnv, encoding: "utf8" });
    expect(JSON.parse(result)).toEqual(enabled ? [{ source: "/api/pilot/:path*", destination: "http://pilot-api:8000/api/pilot/:path*" }] : []);
  });
  it("blocks direct pilot transport calls by default before fetch", async () => {
    const fetcher = vi.fn(async () => new Response("{}")); vi.stubGlobal("fetch", fetcher);
    await expect(pilotApi("monitor")).rejects.toThrow(/локальн/i);
    expect(fetcher).not.toHaveBeenCalled();
  });
});

// Exercise transport's last guard independently of route rendering.
describe("loopback-only research transport", () => {
  it.each([
    ["localhost", true], ["127.0.0.1", true], ["[::1]", true],
    ["localhost.example.org", false], ["example.org", false], ["192.168.1.10", false],
  ])("hostname %s allows requests: %s", async (hostname, allowed) => {
    vi.stubEnv("NEXT_PUBLIC_PILOT_MODE", "true"); vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local"); vi.stubEnv("NODE_ENV", "development");
    vi.stubGlobal("window", { location: { hostname } });
    vi.resetModules();
    const { pilotApi: localApi } = await import("./api");
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ index: 1 }))); vi.stubGlobal("fetch", fetcher);
    if (allowed) {
      await expect(localApi("replay", "POST", { action: "step" })).resolves.toEqual({ index: 1 });
      expect(fetcher).toHaveBeenCalledWith("/api/pilot/replay", expect.objectContaining({ method: "POST", body: '{"action":"step"}' }));
    } else {
      await expect(localApi("replay", "POST", { action: "step" })).rejects.toThrow(/локальн/i);
      expect(fetcher).not.toHaveBeenCalled();
    }
  });
  it("does not assume localhost during server rendering", async () => {
    vi.stubEnv("NEXT_PUBLIC_PILOT_MODE", "true"); vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local"); vi.stubEnv("NODE_ENV", "development");
    vi.stubGlobal("window", undefined); vi.resetModules();
    const { pilotApi: localApi } = await import("./api");
    const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
    await expect(localApi("monitor")).rejects.toThrow(/локальн/i);
    expect(fetcher).not.toHaveBeenCalled();
  });
});

"use client";

import { useSyncExternalStore } from "react";
import { env } from "@/config/env";

// Configuration is necessary but not sufficient: research must also be opened
// on loopback. No hostname suffix matching and no SSR assumption of localhost.
export function isLocalResearchHost(): boolean {
  return env.pilotModeEnabled && typeof window !== "undefined" &&
    ["localhost", "127.0.0.1", "[::1]", "::1"].includes(window.location.hostname);
}
const subscribe = () => () => {};
export function useLocalResearch(): boolean {
  return useSyncExternalStore(subscribe, isLocalResearchHost, () => false);
}

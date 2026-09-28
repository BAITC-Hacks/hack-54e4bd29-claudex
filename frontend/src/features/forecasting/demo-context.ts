/** A presentation flag for an explicitly isolated synthetic demo build. */
export function syntheticDemoLabelEnabled(appEnv?: string, flag?: string): boolean {
  return (appEnv === "local" || appEnv === "test") && flag === "true";
}

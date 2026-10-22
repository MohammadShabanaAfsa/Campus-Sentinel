export function diagnostic(scope: string, message: string) {
  if (process.env.NODE_ENV === "development") console.info(`[${scope}] ${message}`);
}

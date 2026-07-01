export function formatError(e: unknown, fallback = "Something went wrong — try again."): string {
  if (e instanceof Error) {
    if (!e.message) return fallback;
    if (/^TypeError|^NetworkError/i.test(e.message)) return "Network error — check your connection.";
    if (/timed out/i.test(e.message)) return "Request timed out — try again.";
    if (/Unauthorized/i.test(e.message)) return "Your session has expired.";
    return e.message;
  }
  if (typeof e === "string" && e.trim()) return e;
  return fallback;
}

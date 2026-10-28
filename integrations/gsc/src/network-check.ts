/** No tokens or account data are sent. Checks whether Google API endpoints
 * return Google's expected JSON auth error to an unauthenticated request. */
const urls = [
  "https://www.googleapis.com/webmasters/v3/sites",
  "https://searchconsole.googleapis.com/webmasters/v3/sites",
];
for (const endpoint of urls) {
  try {
    const response = await fetch(endpoint, {
      headers: { Accept: "application/json" },
      redirect: "manual",
      signal: AbortSignal.timeout(12000),
    });
    const contentType = response.headers.get("content-type") ?? "absent";
    const kind = contentType.toLowerCase().includes("json") ? "json"
      : contentType.toLowerCase().includes("html") ? "html" : "other";
    console.log(JSON.stringify({
      host: new URL(endpoint).hostname,
      httpStatus: response.status,
      responseKind: kind,
      redirected: response.status >= 300 && response.status < 400,
    }));
  } catch (error) {
    console.log(JSON.stringify({
      host: new URL(endpoint).hostname,
      networkError: error instanceof Error ? error.name : "unknown",
    }));
  }
}

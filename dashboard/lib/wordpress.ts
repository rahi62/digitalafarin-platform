export async function checkWordPressConnection(input: { baseUrl: string; username: string; appPassword: string }) {
  const url = new URL("/wp-json/wp/v2/users/me?context=edit", input.baseUrl);
  const response = await fetch(url, {
    headers: {
      Authorization: `Basic ${Buffer.from(`${input.username}:${input.appPassword.replace(/\s+/g, "")}`, "utf8").toString("base64")}`,
      Accept: "application/json",
      "User-Agent": "DigitalAfarin-WP-Agent-Dashboard/0.2",
    },
    cache: "no-store",
    signal: AbortSignal.timeout(20_000),
  });
  const data = await response.json().catch(() => null) as { id?: number; name?: string; roles?: string[]; message?: string } | null;
  if (!response.ok) throw new Error(data?.message || `WordPress returned HTTP ${response.status}`);
  return { id: data?.id, name: data?.name, roles: data?.roles ?? [] };
}

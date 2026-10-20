/** The plain HTTP endpoints; everything else is the socket. */
import { UNPAIRED_TEXT, type SessionSummary } from "./protocol";
import { authHeaders, getServerUrl, setToken } from "./settings";

export async function fetchSessions(): Promise<SessionSummary[]> {
  const base = await getServerUrl();
  if (!base) throw new Error("no server url");
  const res = await fetch(`${base}/sessions`, { headers: await authHeaders() });
  if (res.status === 401) throw new Error(UNPAIRED_TEXT);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as SessionSummary[];
}

/** Trade a code from `vmp pair` for this phone's token, and keep it. Throws the server's own words. */
export async function pair(code: string, name: string): Promise<{ token: string; name: string }> {
  const base = await getServerUrl();
  if (!base) throw new Error("no server url");
  const res = await fetch(`${base}/pair`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ code, name }),
  });
  const body = (await res.json().catch(() => ({}))) as { token?: string; name?: string; error?: string };
  if (!res.ok || !body.token) throw new Error(body.error ?? `HTTP ${res.status}`);
  await setToken(body.token);
  return { token: body.token, name: body.name ?? name };
}

export async function sessionLink(sessionId: string): Promise<string> {
  return `${await getServerUrl()}/s/${sessionId}`;
}

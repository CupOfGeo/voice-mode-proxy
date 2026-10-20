/** Pure URL helpers, kept free of native imports so they can be unit tested. */

/** Trim, add https:// when the scheme is missing, drop a trailing slash. */
export function normalizeServerUrl(url: string): string {
  let u = url.trim();
  if (!u) return "";
  if (!/^https?:\/\//i.test(u)) u = `https://${u}`;
  return u.replace(/\/+$/, "");
}

export function websocketUrl(serverUrl: string): string {
  return serverUrl.replace(/^http/i, "ws") + "/ws";
}

/** localhost, .local, and the private ranges (RFC 1918, link-local, Tailscale's 100.64/10, IPv6 ULA). */
export function isPrivateHost(hostname: string): boolean {
  const h = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (h === "localhost" || h.endsWith(".local") || h === "::1") return true;
  if (/^f[cd][0-9a-f]{2}:/.test(h)) return true;
  const m = /^(\d+)\.(\d+)\.(\d+)\.(\d+)$/.exec(h);
  if (!m) return false;
  const [a, b] = [Number(m[1]), Number(m[2])];
  return (
    a === 10 ||
    a === 127 ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168) ||
    (a === 169 && b === 254) ||
    (a === 100 && b >= 64 && b <= 127)
  );
}

export const PLAIN_HTTP_TEXT =
  "Plain http is only allowed for addresses on your own network (192.168…, 10…, .local, or a Tailscale IP). " +
  "Over the internet, use Tailscale Serve or a TLS reverse proxy so the pairing token is not sent in the clear.";

/** Why a normalized URL must not be used, or null when it is fine. */
export function plainHttpProblem(serverUrl: string): string | null {
  const m = /^http:\/\/([^/:?#]+)/i.exec(serverUrl);
  if (!m) return null;
  return isPrivateHost(m[1]) ? null : PLAIN_HTTP_TEXT;
}

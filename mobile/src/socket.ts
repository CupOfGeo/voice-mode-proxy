/**
 * Exactly one socket at a time, outside React. Ported from connect() in web/index.html.
 * iOS suspends the app when the screen locks; on return the old socket may be dead,
 * half-open, or fine. Whatever it is, it gets closed and replaced, and its handlers are
 * ignored, so a message is never handled twice.
 */
import { AppState } from "react-native";
import { parseServerMessage, UNPAIRED_CLOSE, type ClientMessage } from "./protocol";
import { DemoServer } from "./demo";
import { authHeaders, getDemoMode, getServerUrl, websocketUrl } from "./settings";
import { useStore } from "./store";

/** React Native's WebSocket takes request headers as a third argument (the pairing token
 *  rides in one); the DOM typing that tsc sees does not know that. */
type RNWebSocketCtor = new (
  uri: string,
  protocols?: string | string[] | null,
  options?: { headers: Record<string, string> } | null,
) => WebSocket;
const RNWebSocket = WebSocket as unknown as RNWebSocketCtor;

let ws: WebSocket | null = null;
let demo: DemoServer | null = null; // demo mode: the in-process fake instead of a socket
let backoff = 1000;
let timer: ReturnType<typeof setTimeout> | null = null;
let started = false;
let failedSinceOpen = 0; // closes without an open; the first one gets a note, the rest stay quiet
let binaryHandler: ((buf: ArrayBuffer) => void) | null = null;
const openHooks = new Set<() => void>();

/** Audio frames go here (step 4). Until then they are dropped. */
export function setBinaryHandler(fn: ((buf: ArrayBuffer) => void) | null): void {
  binaryHandler = fn;
}

/** Runs after every successful open, e.g. to re-send audio_start. */
export function onOpen(fn: () => void): () => void {
  openHooks.add(fn);
  return () => openHooks.delete(fn);
}

export function isOpen(): boolean {
  return !!demo || (!!ws && ws.readyState === WebSocket.OPEN);
}

export function isDemo(): boolean {
  return !!demo;
}

export function send(msg: ClientMessage): boolean {
  if (demo) {
    demo.handle(msg);
    return true;
  }
  if (isOpen()) {
    ws!.send(JSON.stringify(msg));
    return true;
  }
  useStore.getState().note("Not connected. Try again in a moment.");
  return false;
}

export function sendBinary(data: ArrayBuffer): boolean {
  if (demo || !isOpen()) return false;
  ws!.send(data);
  return true;
}

/** Playback diagnostics into the server's session log; silent when offline. */
export function clog(text: string): void {
  if (!demo && isOpen()) ws!.send(JSON.stringify({ type: "client_log", text }));
}

function dropSocket(): void {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  if (demo) {
    demo.close();
    demo = null;
  }
  if (ws) {
    const old = ws;
    ws = null;
    old.onopen = old.onmessage = old.onclose = old.onerror = null;
    try {
      old.close();
    } catch {
      // already closed
    }
  }
}

export async function connect(): Promise<void> {
  dropSocket();
  if (await getDemoMode()) {
    const fake = new DemoServer((msg) => {
      if (demo === fake) useStore.getState().handle(msg);
    });
    demo = fake;
    fake.open();
    for (const fn of openHooks) fn();
    return;
  }
  const url = await getServerUrl();
  if (!url) {
    useStore.getState().setConn("off");
    return;
  }
  const sock = new RNWebSocket(websocketUrl(url), null, { headers: await authHeaders() });
  sock.binaryType = "arraybuffer";
  let opened = false;
  sock.onopen = () => {
    if (sock !== ws) return;
    backoff = 1000;
    failedSinceOpen = 0;
    opened = true;
    for (const fn of openHooks) fn();
  };
  sock.onmessage = (m) => {
    if (sock !== ws) return;
    if (m.data instanceof ArrayBuffer) {
      try {
        binaryHandler?.(m.data);
      } catch (e) {
        clog(`audio frame error: ${e}`);
      }
    } else if (typeof m.data === "string") {
      useStore.getState().handle(parseServerMessage(m.data));
    }
  };
  sock.onclose = (e) => {
    if (sock !== ws) return;
    ws = null;
    if (e.code === UNPAIRED_CLOSE) {
      // The server said why in an error row before closing. Retrying would only repeat it;
      // pairing calls reconnect().
      useStore.getState().setConn("unpaired");
      return;
    }
    useStore.getState().setConn("off");
    if (!opened && ++failedSinceOpen === 1) {
      useStore.getState().note(`Cannot reach ${url}. Check the server URL in Settings; retrying quietly.`);
    }
    timer = setTimeout(() => void connect(), backoff);
    backoff = Math.min(backoff * 2, 10000);
  };
  sock.onerror = () => {
    if (sock === ws) sock.close();
  };
  ws = sock;
}

/** After the server URL changes: fresh socket, fresh backoff. */
export function reconnect(): void {
  backoff = 1000;
  failedSinceOpen = 0;
  void connect();
}

/** Call once from App. Connects now and again whenever the app returns to the foreground. */
export function startSocket(): void {
  if (started) return;
  started = true;
  AppState.addEventListener("change", (state) => {
    clog(`app ${state}, socket ${isOpen() ? "open" : "closed"}`); // lock-screen diagnostics
    if (state === "active" && !isOpen() && useStore.getState().conn !== "unpaired") void connect();
  });
  void connect();
}

/**
 * Where the server lives, and the pairing token that lets this phone talk to it.
 * The URL is the http(s) origin, e.g. https://mac.tail1234.ts.net:8443; the app derives
 * ws(s)://.../ws from it. The token (from POST /pair) goes in the keychain, readable after
 * the first unlock so the socket can reconnect with the screen locked.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import type { Health } from "./protocol";
import { normalizeServerUrl } from "./urls";

export { normalizeServerUrl, plainHttpProblem, websocketUrl } from "./urls";

const SERVER_URL_KEY = "server_url";
const DEMO_KEY = "demo_mode";
const TOKEN_KEY = "vmp_token";
const ENV_SERVER_URL = process.env.EXPO_PUBLIC_SERVER_URL ?? "";

export async function getServerUrl(): Promise<string> {
  const stored = await AsyncStorage.getItem(SERVER_URL_KEY);
  return normalizeServerUrl(stored || ENV_SERVER_URL);
}

export async function setServerUrl(url: string): Promise<string> {
  const clean = normalizeServerUrl(url);
  await AsyncStorage.setItem(SERVER_URL_KEY, clean);
  return clean;
}

/** Demo mode: talk to the in-process fake instead of a server (src/demo.ts). */
export async function getDemoMode(): Promise<boolean> {
  return (await AsyncStorage.getItem(DEMO_KEY)) === "1";
}

export async function setDemoMode(on: boolean): Promise<void> {
  await AsyncStorage.setItem(DEMO_KEY, on ? "1" : "0");
}

let tokenCache: string | null | undefined; // the socket reconnects often; read the keychain once

export async function getToken(): Promise<string | null> {
  if (tokenCache === undefined) tokenCache = await SecureStore.getItemAsync(TOKEN_KEY);
  return tokenCache;
}

export async function setToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, token, { keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK });
  tokenCache = token;
}

export async function clearToken(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
  tokenCache = null;
}

/** `Authorization: Bearer` for fetch and the socket; empty until paired. */
export async function authHeaders(): Promise<Record<string, string>> {
  const t = await getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export async function fetchHealth(serverUrl: string): Promise<Health> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    const res = await fetch(`${serverUrl}/health`, { signal: controller.signal, headers: await authHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as Health;
  } finally {
    clearTimeout(timer);
  }
}

import { authHeaders, clearToken, fetchHealth, getToken, setToken } from "../settings";

// jest hoists these above the import
jest.mock("expo-secure-store", () => {
  const m = new Map<string, string>();
  return {
    AFTER_FIRST_UNLOCK: 1,
    getItemAsync: jest.fn(async (k: string) => m.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => void m.set(k, v)),
    deleteItemAsync: jest.fn(async (k: string) => void m.delete(k)),
  };
});
jest.mock("@react-native-async-storage/async-storage", () =>
  jest.requireActual("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);

describe("pairing token", () => {
  it("is absent until paired, then rides in the Authorization header", async () => {
    expect(await getToken()).toBeNull();
    expect(await authHeaders()).toEqual({});
    await setToken("t0k");
    expect(await getToken()).toBe("t0k");
    expect(await authHeaders()).toEqual({ Authorization: "Bearer t0k" });
    await clearToken();
    expect(await authHeaders()).toEqual({});
  });

  it("goes out with the health check", async () => {
    await setToken("abc");
    const fetchMock = jest.fn(async () => ({ ok: true, json: async () => ({ ok: true, protocol: 2 }) }));
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    const h = await fetchHealth("https://mac.example:8443");
    expect(h.protocol).toBe(2);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://mac.example:8443/health");
    expect(init.headers).toEqual({ Authorization: "Bearer abc" });
  });
});

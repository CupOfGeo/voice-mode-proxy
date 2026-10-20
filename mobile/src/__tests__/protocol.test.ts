import { parseAudioFrame } from "../protocol";
import { isPrivateHost, normalizeServerUrl, plainHttpProblem, websocketUrl } from "../urls";

function frame(header: object, samples: number[]): ArrayBuffer {
  const h = new TextEncoder().encode(JSON.stringify(header));
  const out = new Uint8Array(4 + h.length + samples.length * 2);
  new DataView(out.buffer).setUint32(0, h.length);
  out.set(h, 4);
  const pcm = new Int16Array(samples);
  out.set(new Uint8Array(pcm.buffer), 4 + h.length);
  return out.buffer;
}

describe("parseAudioFrame", () => {
  it("reads the header and the samples", () => {
    const f = parseAudioFrame(frame({ id: 7, seq: 2, last: true, sample_rate: 24000 }, [1, -2, 32767]));
    expect(f.header).toEqual({ id: 7, seq: 2, last: true, sample_rate: 24000 });
    expect(Array.from(f.pcm)).toEqual([1, -2, 32767]);
  });

  it("copes with an odd header length", () => {
    // {"id":1,"seq":0,"last":false,"sample_rate":24000} is 49 bytes, so the payload starts at an odd offset
    const header = { id: 1, seq: 0, last: false, sample_rate: 24000 };
    expect(JSON.stringify(header).length % 2).toBe(1);
    const f = parseAudioFrame(frame(header, [100, 200]));
    expect(Array.from(f.pcm)).toEqual([100, 200]);
  });
});

describe("server url", () => {
  it("normalises what the user types", () => {
    expect(normalizeServerUrl("  mac.tail1234.ts.net:8443/ ")).toBe("https://mac.tail1234.ts.net:8443");
    expect(normalizeServerUrl("http://100.64.0.2:8791")).toBe("http://100.64.0.2:8791");
    expect(normalizeServerUrl("")).toBe("");
  });

  it("derives the socket url", () => {
    expect(websocketUrl("https://mac.tail1234.ts.net:8443")).toBe("wss://mac.tail1234.ts.net:8443/ws");
    expect(websocketUrl("http://100.64.0.2:8791")).toBe("ws://100.64.0.2:8791/ws");
  });
});

describe("plain http guard", () => {
  it("knows the private ranges", () => {
    for (const h of ["localhost", "mac.local", "10.0.0.5", "172.16.4.1", "172.31.255.1", "192.168.1.20", "169.254.1.1", "100.64.0.2", "100.127.9.9", "::1", "fd12::1"]) {
      expect(isPrivateHost(h)).toBe(true);
    }
    for (const h of ["8.8.8.8", "172.32.0.1", "100.128.0.1", "example.com", "mac.tail1234.ts.net", "11.0.0.1"]) {
      expect(isPrivateHost(h)).toBe(false);
    }
  });

  it("refuses plain http to a public address", () => {
    expect(plainHttpProblem("https://example.com:8443")).toBeNull();
    expect(plainHttpProblem("http://192.168.1.20:8791")).toBeNull();
    expect(plainHttpProblem("http://100.64.0.2:8791")).toBeNull();
    expect(plainHttpProblem("http://mac.local:8791")).toBeNull();
    expect(plainHttpProblem("http://203.0.113.9:8791")).toMatch(/Plain http/);
    expect(plainHttpProblem("http://proxy.example.com")).toMatch(/Tailscale Serve/);
  });
});

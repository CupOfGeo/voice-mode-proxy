import { DemoServer } from "../demo";
import { PROTOCOL, type ServerMessage } from "../protocol";

jest.useFakeTimers();

function boot() {
  const out: ServerMessage[] = [];
  const srv = new DemoServer((m) => out.push(m));
  srv.open();
  return { srv, out, types: () => out.map((m) => m.type) };
}

describe("DemoServer", () => {
  it("opens like a real server: hello, settings, history", () => {
    const { out, types } = boot();
    expect(types()).toEqual(["hello", "settings", "history"]);
    const hello = out[0] as Extract<ServerMessage, { type: "hello" }>;
    expect(hello.protocol).toBe(PROTOCOL);
    expect(hello.stt).toBe(false);
    expect(hello.tts).toBe(false);
    expect(hello.session?.permission_mode).toBe("default");
  });

  it("runs a turn with a permission card that can be allowed", () => {
    const { srv, out, types } = boot();
    out.length = 0;
    srv.handle({ type: "user_text", text: "list the files" });
    jest.advanceTimersByTime(2000);
    expect(types()).toEqual(["transcript", "status", "tool", "permission_request"]);
    const req = out[3] as Extract<ServerMessage, { type: "permission_request" }>;
    out.length = 0;
    srv.handle({ type: "permission_response", request_id: req.request_id, allow: true, mode: "acceptEdits" });
    jest.advanceTimersByTime(1000);
    expect(types()).toEqual(["permission_resolved", "session", "speak", "status", "turn_done"]);
    expect((out[1] as Extract<ServerMessage, { type: "session" }>).permission_mode).toBe("acceptEdits");
    expect((out[3] as Extract<ServerMessage, { type: "status" }>).state).toBe("idle");
  });

  it("skips the card in auto mode and rejects a stale answer", () => {
    const { srv, out, types } = boot();
    srv.handle({ type: "permission_mode", mode: "auto" });
    out.length = 0;
    srv.handle({ type: "user_text", text: "go" });
    jest.advanceTimersByTime(2000);
    expect(types()).toEqual(["transcript", "status", "tool", "speak", "status", "turn_done"]);
    out.length = 0;
    srv.handle({ type: "permission_response", request_id: "nope", allow: true, mode: null });
    expect(types()).toEqual(["error"]);
  });

  it("stops delivering after close", () => {
    const { srv, out } = boot();
    srv.handle({ type: "user_text", text: "go" });
    srv.close();
    const n = out.length;
    jest.advanceTimersByTime(5000);
    expect(out.length).toBe(n);
  });
});

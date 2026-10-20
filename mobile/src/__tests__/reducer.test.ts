import { initialState, reduce, type State } from "../reducer";
import { PROTOCOL, type PermissionRequest, type Session } from "../protocol";

const session: Session = {
  type: "session",
  session_id: "abcdef12-3456",
  cwd: "/Users/me/Code/x",
  project: "x",
  title: "Fix the thing",
  resumed_from: null,
  model: "claude-sonnet-5",
  busy: false,
  permission_mode: "auto",
};

const perm: PermissionRequest = {
  type: "permission_request",
  request_id: "r1",
  tool: "Bash",
  spoken: "It wants to run a command: list files.",
  detail: { command: "ls" },
};

function apply(s: State, ...msgs: Parameters<typeof reduce>[1][]): State {
  return msgs.reduce((acc, m) => ({ ...acc, ...reduce(acc, m) }), s);
}

describe("reduce", () => {
  it("hello sets projects, session, server features and pending", () => {
    const s = apply(initialState, {
      type: "hello",
      session: { ...session, busy: true },
      projects: [{ name: "x", path: "/x" }],
      stt: true,
      tts: false,
      pending: [perm],
    });
    expect(s.conn).toBe("working");
    expect(s.projects).toHaveLength(1);
    expect(s.serverStt).toBe(true);
    expect(s.serverTts).toBe(false);
    expect(s.pending).toEqual([perm]);
  });

  it("hello checks the protocol version", () => {
    const hello = { type: "hello" as const, session: null, projects: [], stt: true, tts: true, pending: [] };
    let s = apply(initialState, { ...hello, protocol: PROTOCOL });
    expect(s.mismatch).toBeNull();
    expect(s.rows).toHaveLength(0);
    s = apply(initialState, hello); // a server from before the field existed
    expect(s.mismatch).toBe("old");
    expect(s.rows).toHaveLength(1);
    expect(s.rows[0].text).toMatch(/too old/);
    s = apply(s, hello); // the same mismatch on reconnect is not repeated
    expect(s.rows).toHaveLength(1);
    s = apply(initialState, { ...hello, protocol: 99 });
    expect(s.mismatch).toBe("new");
    s = apply(s, { ...hello, protocol: PROTOCOL }); // the server was updated
    expect(s.mismatch).toBeNull();
  });

  it("hello after an unpaired close clears the state", () => {
    const hello = { type: "hello" as const, session: null, projects: [], stt: true, tts: true, pending: [], protocol: PROTOCOL };
    const s = apply({ ...initialState, conn: "unpaired" }, hello);
    expect(s.conn).toBe("idle");
  });

  it("hello without a session is idle", () => {
    const s = apply(initialState, { type: "hello", session: null, projects: [], stt: false, tts: false, pending: [] });
    expect(s.conn).toBe("idle");
    expect(s.session).toBeNull();
  });

  it("settings event is kept whole for the settings screen", () => {
    const values = {
      speech_rate: 1.15,
      kokoro_voice: "af_heart",
      vad_silence_ms: 2000,
      vad_min_speech_ms: 500,
      vad_barge_in_ms: 1500,
      voice_prompt: "Be brief.",
    };
    const s = apply(initialState, { type: "settings", values: { ...values, speech_rate: 1.3 }, defaults: values, voices: ["af_heart"] });
    expect(s.settings?.values.speech_rate).toBe(1.3);
    expect(s.settings?.defaults.speech_rate).toBe(1.15);
    expect(s.settings?.voices).toEqual(["af_heart"]);
  });

  it("history replaces the transcript and live events append", () => {
    let s = apply(initialState, { type: "transcript", role: "user", text: "old" });
    s = apply(s, {
      type: "history",
      items: [
        { type: "transcript", role: "user", text: "hi" },
        { type: "speak", kind: "reply", text: "hello" },
      ],
    });
    expect(s.rows.map((r) => r.text)).toEqual(["hi", "hello"]);
    s = apply(s, { type: "tool", name: "Read", target: "a.py" }, { type: "heard", text: "yo", seconds: 1 });
    expect(s.rows.map((r) => r.kind)).toEqual(["user", "speak", "tool", "heard"]);
    expect(new Set(s.rows.map((r) => r.id)).size).toBe(4);
  });

  it("replayed events are not drawn again", () => {
    const s = apply(
      initialState,
      { type: "speak", kind: "reply", text: "again", replay: true },
      { type: "transcript", role: "assistant", text: "again", replay: true },
      { type: "tool", name: "Read", target: "x", replay: true },
    );
    expect(s.rows).toHaveLength(0);
  });

  it("permission requests queue and resolve", () => {
    let s = apply(initialState, perm, { ...perm, request_id: "r2" });
    expect(s.pending.map((p) => p.request_id)).toEqual(["r1", "r2"]);
    s = apply(s, { type: "permission_resolved", request_id: "r1", allow: true });
    expect(s.pending.map((p) => p.request_id)).toEqual(["r2"]);
  });

  it("status and errors", () => {
    let s = apply(initialState, session, { type: "status", state: "working" });
    expect(s.conn).toBe("working");
    s = apply(s, { type: "error", message: "boom" }, { type: "vad", speech: true });
    expect(s.rows[0]).toMatchObject({ kind: "speak", speakKind: "error", text: "boom" });
    expect(s.speech).toBe(true);
  });
});

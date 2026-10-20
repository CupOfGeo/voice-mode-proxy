/**
 * Demo mode: an in-process fake that speaks the server protocol, so the whole app can be
 * tried with no server and no network (phase two, step 4 of IOS-PLAN.md). It is also handy
 * for UI work without the Mac running. It reports no speech recognition and no server
 * voice, so the mic stays off and replies are read by the phone's own voice.
 *
 * The reducer, screens and audio code do not know it exists; socket.ts routes to it.
 */
import type { ClientMessage, PermissionMode, PermissionRequest, ServerMessage, Session, SettingsValues } from "./protocol";
import { PROTOCOL } from "./protocol";

export const DEMO_PROJECT = { name: "demo-project", path: "/demo/demo-project" };

const DEFAULTS: SettingsValues = {
  speech_rate: 1.15,
  kokoro_voice: "af_heart",
  vad_silence_ms: 2000,
  vad_min_speech_ms: 500,
  vad_barge_in_ms: 1500,
  voice_prompt: "You are being used through a voice interface. Keep replies to two or three short spoken sentences.",
};

const REPLIES = [
  "Done. I listed the project folder: there are twelve entries, mostly source files and a README.",
  "I looked at that. The change is small, two files, and the tests still pass.",
  "Understood. I made the edit and left a note in the file explaining why.",
];

export class DemoServer {
  private session: Session;
  private values: SettingsValues = { ...DEFAULTS };
  private pending: PermissionRequest | null = null;
  private turn = 0;
  private timers = new Set<ReturnType<typeof setTimeout>>();
  private closed = false;

  constructor(private readonly deliver: (msg: ServerMessage) => void) {
    this.session = this.newSession();
  }

  private newSession(): Session {
    return {
      type: "session",
      session_id: `demo-${Date.now().toString(36)}`,
      cwd: DEMO_PROJECT.path,
      project: DEMO_PROJECT.name,
      title: "Demo session",
      resumed_from: null,
      model: "demo",
      busy: false,
      permission_mode: "default",
    };
  }

  private later(ms: number, fn: () => void): void {
    const t = setTimeout(() => {
      this.timers.delete(t);
      if (!this.closed) fn();
    }, ms);
    this.timers.add(t);
  }

  open(): void {
    this.deliver({
      type: "hello",
      protocol: PROTOCOL,
      session: this.session,
      projects: [DEMO_PROJECT],
      stt: false,
      tts: false,
      pending: this.pending ? [this.pending] : [],
    });
    this.deliver({ type: "settings", values: this.values, defaults: DEFAULTS, voices: [DEFAULTS.kokoro_voice] });
    this.deliver({
      type: "history",
      items: [
        { type: "speak", kind: "system", text: "Demo mode. Nothing here reaches a real server. Type an instruction to see a turn, including a permission card." },
      ],
    });
  }

  close(): void {
    this.closed = true;
    for (const t of this.timers) clearTimeout(t);
    this.timers.clear();
  }

  handle(msg: ClientMessage): void {
    switch (msg.type) {
      case "ping":
        this.deliver({ type: "pong" });
        return;
      case "user_text":
        this.runTurn(msg.text);
        return;
      case "session_new":
      case "session_resume":
        this.session = this.newSession();
        this.pending = null;
        this.deliver(this.session);
        this.deliver({ type: "history", items: [] });
        return;
      case "permission_mode":
        this.session = { ...this.session, permission_mode: msg.mode };
        this.deliver(this.session);
        return;
      case "permission_response":
        this.resolvePermission(msg.request_id, msg.allow, msg.mode);
        return;
      case "settings":
        this.values = { ...this.values, ...msg.values };
        this.deliver({ type: "settings", values: this.values, defaults: DEFAULTS, voices: [DEFAULTS.kokoro_voice] });
        return;
      case "interrupt":
        if (this.session.busy) this.finishTurn("Stopped.", "system");
        return;
      case "audio_start":
        this.deliver({ type: "error", message: "speech recognition is disabled in demo mode" });
        return;
      default:
        return; // audio_stop, tts_cancel, playing, client_log: nothing to do
    }
  }

  private setBusy(busy: boolean): void {
    this.session = { ...this.session, busy };
    this.deliver({ type: "status", state: busy ? "working" : "idle" });
  }

  private runTurn(text: string): void {
    if (this.session.busy) return;
    this.turn++;
    this.deliver({ type: "transcript", role: "user", text });
    this.setBusy(true);
    this.later(700, () => this.deliver({ type: "tool", name: "Read", target: "README.md" }));
    if (this.session.permission_mode === "auto") {
      this.later(1600, () => this.finishTurn(REPLIES[this.turn % REPLIES.length], "reply"));
      return;
    }
    this.later(1400, () => {
      this.pending = {
        type: "permission_request",
        request_id: `demo-req-${this.turn}`,
        tool: "Bash",
        spoken: "It wants to run a command: list the project folder.",
        detail: { command: "ls -la", description: "List the project folder" },
      };
      this.deliver(this.pending);
    });
  }

  private resolvePermission(requestId: string, allow: boolean, mode: PermissionMode | null): void {
    if (!this.pending || this.pending.request_id !== requestId) {
      this.deliver({ type: "error", message: "no such pending permission request" });
      return;
    }
    this.pending = null;
    this.deliver({ type: "permission_resolved", request_id: requestId, allow });
    if (mode === "auto" || mode === "acceptEdits" || mode === "default") {
      this.session = { ...this.session, permission_mode: mode };
      this.deliver(this.session);
    }
    this.later(900, () =>
      allow ? this.finishTurn(REPLIES[this.turn % REPLIES.length], "reply") : this.finishTurn("Okay, I did not run it. Tell me what you would rather I do.", "reply"),
    );
  }

  private finishTurn(text: string, kind: "reply" | "system"): void {
    this.deliver({ type: "speak", kind, text });
    this.setBusy(false);
    this.deliver({ type: "turn_done" });
  }
}

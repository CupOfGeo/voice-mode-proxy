/**
 * Pure state and the reducer that applies one server message to it. No React, no native
 * imports, so it is unit tested directly. store.ts wraps it for the UI.
 * Mirrors handle() in web/index.html.
 */
import {
  MISMATCH_TEXT,
  protocolMismatch,
  type PermissionRequest,
  type Project,
  type ProtocolMismatch,
  type ServerMessage,
  type Session,
  type SettingsEvent,
  type PermissionDetail,
  type SpeakKind,
} from "./protocol";

/** "unpaired": the server closed the socket with UNPAIRED_CLOSE; no retry until the phone pairs. */
export type ConnState = "off" | "unpaired" | "idle" | "working";

export type Row =
  | { id: number; kind: "user" | "assistant"; text: string }
  | { id: number; kind: "speak"; speakKind: SpeakKind; text: string }
  | { id: number; kind: "tool"; text: string; detail?: PermissionDetail }
  | { id: number; kind: "heard"; text: string };

export interface State {
  conn: ConnState;
  session: Session | null;
  projects: Project[];
  serverStt: boolean;
  serverTts: boolean;
  /** Set from hello; while non-null the mic and composer are off and a row says why. */
  mismatch: ProtocolMismatch;
  /** The server's tunables, null until the first settings event after hello. */
  settings: SettingsEvent | null;
  rows: Row[];
  pending: PermissionRequest[];
  speech: boolean;
  /** Client preferences, in memory like the page. */
  voiceOn: boolean;
  /** Keep the mic open while a reply plays so you can talk over it. Off by default: the
   *  speaker leaks into the mic and reads as an interruption. */
  bargeIn: boolean;
  micOn: boolean;
}

export const initialState: State = {
  conn: "off",
  session: null,
  projects: [],
  serverStt: false,
  serverTts: false,
  mismatch: null,
  settings: null,
  rows: [],
  pending: [],
  speech: false,
  voiceOn: true,
  bargeIn: false,
  micOn: false,
};

/** Row without its id; distributes over the union so each variant keeps its own fields. */
type RowInput = Row extends infer R ? (R extends Row ? Omit<R, "id"> : never) : never;

let nextRowId = 1;
export function row(r: RowInput): Row {
  return { ...r, id: nextRowId++ } as Row;
}

const MAX_ROWS = 500;
function append(rows: Row[], r: Row): Row[] {
  const out = rows.length >= MAX_ROWS ? rows.slice(rows.length - MAX_ROWS + 1) : rows;
  return [...out, r];
}

/** A local note in the transcript, e.g. "Not connected". */
export function systemRow(text: string): Row {
  return row({ kind: "speak", speakKind: "system", text });
}

/** The user tapped Allow or Deny on a request: drop it locally and note it in the transcript. */
export function answered(s: State, requestId: string, allow: boolean): Partial<State> {
  const req = s.pending.find((p) => p.request_id === requestId);
  if (!req) return {};
  return {
    pending: s.pending.filter((p) => p.request_id !== requestId),
    rows: append(s.rows, row({ kind: "tool", text: `${allow ? "allowed" : "denied"}: ${req.spoken}` })),
  };
}

export function reduce(s: State, msg: ServerMessage): Partial<State> {
  switch (msg.type) {
    case "hello": {
      const session = msg.session;
      const mismatch = protocolMismatch(msg.protocol);
      return {
        projects: msg.projects ?? [],
        session,
        serverStt: !!msg.stt,
        serverTts: !!msg.tts,
        mismatch,
        conn: session?.busy ? "working" : "idle",
        pending: msg.pending ?? [],
        // Once per hello, not on every reconnect that finds the same state.
        rows: mismatch && s.mismatch !== mismatch ? append(s.rows, systemRow(MISMATCH_TEXT[mismatch])) : s.rows,
      };
    }
    case "session":
      return { session: msg, conn: msg.busy ? "working" : "idle" };
    case "projects":
      return { projects: msg.projects ?? [] };
    case "settings":
      return { settings: msg };
    case "status":
      return { conn: msg.state };
    case "history":
      return {
        rows: (msg.items ?? []).map((it) =>
          it.type === "transcript"
            ? row({ kind: it.role, text: it.text })
            : row({ kind: "speak", speakKind: it.kind, text: it.text }),
        ),
      };
    case "transcript":
      return msg.replay ? {} : { rows: append(s.rows, row({ kind: msg.role, text: msg.text })) };
    case "tool":
      return msg.replay
        ? {}
        : {
            rows: append(
              s.rows,
              row({ kind: "tool", text: `${msg.name} ${msg.target}`.trim(), detail: msg.detail }),
            ),
          };
    case "speak":
      return msg.replay ? {} : { rows: append(s.rows, row({ kind: "speak", speakKind: msg.kind, text: msg.text })) };
    case "permission_request":
      return { pending: [...s.pending, msg] };
    case "permission_resolved":
      return { pending: s.pending.filter((p) => p.request_id !== msg.request_id) };
    case "error":
      return { rows: append(s.rows, row({ kind: "speak", speakKind: "error", text: msg.message })) };
    case "heard":
      return { rows: append(s.rows, row({ kind: "heard", text: msg.text })) };
    case "vad":
      return { speech: !!msg.speech };
    case "turn_done":
    case "dropped":
    case "result":
    case "pong":
      return {};
  }
}

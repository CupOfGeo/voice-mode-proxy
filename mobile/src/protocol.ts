/**
 * The WebSocket protocol, mirrored from the docstring at the top of
 * voice_mode_proxy/server.py. Keep the two in step.
 */

/** The contract version this app speaks; the server sends its own in hello and /health.
 *  Older servers (2026-09-22 and before) send none, which counts as 0. */
export const PROTOCOL = 2;

/** The close code the server uses for a socket without a valid pairing token. */
export const UNPAIRED_CLOSE = 4401;
export const UNPAIRED_TEXT = "This phone is not paired with the server. Run `vmp pair` on the Mac and enter the code.";

export type PermissionMode = "auto" | "default" | "acceptEdits";
export type SpeakKind = "edits" | "reply" | "error" | "system";
export type StatusState = "working" | "idle";

// ------------------------------------------------------------------ client -> server

export type ClientMessage =
  | { type: "user_text"; text: string }
  | { type: "session_new"; cwd?: string }
  | { type: "session_resume"; session_id: string; cwd?: string }
  | { type: "permission_response"; request_id: string; allow: boolean; mode: PermissionMode | null }
  | { type: "permission_mode"; mode: PermissionMode }
  | { type: "settings"; values: Partial<SettingsValues> }
  | { type: "projects_reload" }
  | { type: "session_restart" }
  | { type: "interrupt" }
  | { type: "audio_start"; sample_rate: 16000 }
  | { type: "audio_stop" }
  | { type: "tts_cancel"; id: number }
  | { type: "playing"; on: boolean }
  | { type: "client_log"; text: string }
  | { type: "ping" };

// ------------------------------------------------------------------ server -> client

export interface Project {
  name: string;
  path: string;
}

export interface Session {
  type: "session";
  session_id: string;
  cwd: string;
  project: string;
  title: string | null;
  resumed_from: string | null;
  model: string | null;
  busy: boolean;
  permission_mode: PermissionMode;
}

/** What GET /sessions returns, one row per past session, newest first. */
export interface SessionSummary {
  session_id: string;
  updated: string;
  cwd?: string;
  started?: string;
  resumed_from?: string | null;
  first_prompt?: string;
  title?: string;
}

/** What GET /health returns. */
export interface Health {
  ok: boolean;
  protocol?: number;
  /** Only present when the request carried a valid pairing token. */
  session?: Session | null;
  clients: number;
  whisper: string | null;
  tts: string | null;
}

/** Server-side tunables the phone may change; voice_mode_proxy/tunables.py has the ranges. */
export interface SettingsValues {
  speech_rate: number;
  kokoro_voice: string;
  vad_silence_ms: number;
  vad_min_speech_ms: number;
  vad_barge_in_ms: number;
  voice_prompt: string;
}

/** Sent after hello and after every change, to every client. */
export interface SettingsEvent {
  type: "settings";
  values: SettingsValues;
  /** What config.toml says; setting a key back to this clears the override. */
  defaults: SettingsValues;
  /** Kokoro voice names, empty when the server has no TTS. */
  voices: string[];
}

export type PermissionDetail =
  | { command: string; description?: string | null }
  | { file: string; edits: { old: string; new: string }[] }
  | { file: string; bytes: number }
  | Record<string, unknown>;

export interface PermissionRequest {
  type: "permission_request";
  request_id: string;
  tool: string;
  spoken: string;
  detail: PermissionDetail;
  /** Present when the server is voicing this request; audio frames carry the same id. */
  tts?: number;
}

export interface TranscriptEvent {
  type: "transcript";
  role: "user" | "assistant";
  text: string;
  replay?: boolean;
}

export interface SpeakEvent {
  type: "speak";
  kind: SpeakKind;
  text: string;
  tts?: number;
  replay?: boolean;
}

export type HistoryItem = TranscriptEvent | SpeakEvent;

export type ServerMessage =
  | {
      type: "hello";
      protocol?: number;
      session: Session | null;
      projects: Project[];
      stt: boolean;
      tts: boolean;
      pending: PermissionRequest[];
    }
  | Session
  | { type: "projects"; projects: Project[] }
  | SettingsEvent
  | { type: "history"; items: HistoryItem[] }
  | { type: "status"; state: StatusState }
  | TranscriptEvent
  | {
      type: "tool";
      name: string;
      target: string;
      spoken?: string;
      detail?: PermissionDetail;
      tts?: number;
      replay?: boolean;
    }
  | SpeakEvent
  | PermissionRequest
  | { type: "permission_resolved"; request_id: string; allow: boolean }
  | { type: "result"; [key: string]: unknown }
  | { type: "turn_done" }
  | { type: "error"; message: string }
  | { type: "heard"; text: string; seconds: number }
  | { type: "dropped"; text: string; seconds: number }
  | { type: "vad"; speech: boolean }
  | { type: "pong" };

// ------------------------------------------------------------------ binary audio frames

/** One sentence of synthesised speech: a 4-byte big-endian header length, the JSON
 *  header, then mono PCM16 samples. `id` matches the `tts` field of the event it voices. */
export interface AudioFrameHeader {
  id: number;
  seq: number;
  last: boolean;
  sample_rate: number;
}

export interface AudioFrame {
  header: AudioFrameHeader;
  /** Samples as Int16. A copy, because the payload offset in the frame is not always even. */
  pcm: Int16Array;
}

export function parseAudioFrame(buf: ArrayBuffer): AudioFrame {
  const view = new DataView(buf);
  const hlen = view.getUint32(0);
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hlen))) as AudioFrameHeader;
  const pcm = new Int16Array(buf.slice(4 + hlen));
  return { header, pcm };
}

/** "old" when the server predates this app, "new" when it is ahead, null when they match. */
export type ProtocolMismatch = "old" | "new" | null;

export function protocolMismatch(serverProtocol: number | undefined): ProtocolMismatch {
  const p = serverProtocol ?? 0;
  return p < PROTOCOL ? "old" : p > PROTOCOL ? "new" : null;
}

export const MISMATCH_TEXT: Record<"old" | "new", string> = {
  old: "The server is too old for this app. Update it on the Mac (git pull, then restart the proxy).",
  new: "The server is newer than this app. Update the app.",
};

export function parseServerMessage(text: string): ServerMessage {
  return JSON.parse(text) as ServerMessage;
}

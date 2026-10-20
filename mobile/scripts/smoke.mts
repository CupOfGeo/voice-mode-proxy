// Connects to a running proxy, feeds three seconds of its messages through the app's
// reducer, and prints the resulting state. Run: node scripts/smoke.mts [ws://host:port/ws]
import { initialState, reduce, type State } from "../src/reducer.ts";
import { parseAudioFrame, parseServerMessage } from "../src/protocol.ts";

const url = process.argv[2] ?? "ws://127.0.0.1:8791/ws";
let state: State = initialState;
const seen: Record<string, number> = {};
const ws = new WebSocket(url);
ws.binaryType = "arraybuffer";
ws.onmessage = (m) => {
  if (m.data instanceof ArrayBuffer) {
    const f = parseAudioFrame(m.data);
    seen[`audio(${f.header.sample_rate})`] = (seen[`audio(${f.header.sample_rate})`] ?? 0) + 1;
    return;
  }
  const msg = parseServerMessage(String(m.data));
  seen[msg.type] = (seen[msg.type] ?? 0) + 1;
  state = { ...state, ...reduce(state, msg) };
};
ws.onerror = (e) => console.error("socket error", e);
setTimeout(() => {
  ws.close();
  console.log(JSON.stringify({ seen, conn: state.conn, session: state.session && { project: state.session.project, title: state.session.title, mode: state.session.permission_mode }, projects: state.projects.length, stt: state.serverStt, tts: state.serverTts, rows: state.rows.length, kinds: [...new Set(state.rows.map((r) => r.kind))], pending: state.pending.length }, null, 1));
}, 3000);

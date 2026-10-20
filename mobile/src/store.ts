import { create } from "zustand";
import type { ServerMessage } from "./protocol";
import { stopSpeaking } from "./audio/player";
import { effects } from "./effects";
import { answered, initialState, reduce, systemRow, row, type Row, type State } from "./reducer";

interface Store extends State {
  handle: (msg: ServerMessage) => void;
  note: (text: string) => void;
  setConn: (conn: State["conn"]) => void;
  answered: (requestId: string, allow: boolean) => void;
  setVoice: (on: boolean) => void;
  setBargeIn: (on: boolean) => void;
  setMic: (on: boolean) => void;
}

export const useStore = create<Store>((set, get) => ({
  ...initialState,
  handle: (msg) => {
    set(reduce(get(), msg));
    const note = effects(msg, get());
    if (note) set((s) => ({ rows: [...s.rows, row({ kind: "tool", text: note })] }));
  },
  note: (text) => set((s) => ({ rows: [...s.rows, systemRow(text)] })),
  setConn: (conn) => set({ conn }),
  answered: (requestId, allow) => set(answered(get(), requestId, allow)),
  setVoice: (voiceOn) => {
    if (!voiceOn) stopSpeaking("voice off");
    set({ voiceOn });
  },
  setBargeIn: (bargeIn) => set({ bargeIn }),
  setMic: (micOn) => set({ micOn, speech: micOn && get().speech }),
}));

export type { Row, State };

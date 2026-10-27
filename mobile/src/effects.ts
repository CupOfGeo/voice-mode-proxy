/**
 * Side effects of a server message, applied after the reducer: what to say and when to
 * shut up. Kept apart from the reducer so the reducer stays pure. Returns a note for the
 * transcript when something worth showing happened.
 */
import { hear, isSpeaking, playCue, stopSpeaking } from "./audio/player";
import type { ServerMessage } from "./protocol";
import type { State } from "./reducer";

export function effects(msg: ServerMessage, state: State): string | undefined {
  switch (msg.type) {
    case "hello": {
      const first = msg.pending?.[0];
      if (first) hear(first.spoken, first.tts);
      return;
    }
    case "speak":
      hear(msg.text, msg.tts);
      return;
    case "tool":
      if (!msg.replay && msg.spoken) hear(msg.spoken, msg.tts);
      return;
    case "permission_request":
      hear(msg.spoken, msg.tts);
      return;
    case "heard": // your words went through
      playCue("heard");
      return;
    case "dropped": // too garbled to send; a quick cue so you know to say it again
      playCue("miss");
      return `didn't catch: "${msg.text}"`;
    case "vad":
      if (msg.speech && state.bargeIn && isSpeaking()) {
        stopSpeaking("barge-in");
        return "stopped speaking: heard you talking";
      }
      return;
    default:
      return;
  }
}

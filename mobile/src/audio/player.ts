/**
 * Speech out. Ported from the "speech out" block of web/index.html.
 *
 * The server sends one PCM16 frame per sentence over the socket; each is turned into an
 * AudioBuffer and played in order through a single AudioContext. `playing` on/off is
 * reported to the server so it can gate barge-in. When the server has no voice loaded,
 * the phone's own voice (expo-speech) reads the text instead.
 */
import { AudioContext, AudioManager, type AudioBuffer, type AudioBufferSourceNode } from "react-native-audio-api";
import * as Speech from "expo-speech";
import { parseAudioFrame } from "../protocol";
import { clog, send } from "../socket";
import { useStore } from "../store";
import { SpeechQueue } from "./queue";

const q = new SpeechQueue<AudioBuffer>();
let ctx: AudioContext | null = null;
let source: AudioBufferSourceNode | null = null;
let reportedPlaying = false;
let sessionReady = false;

/** playAndRecord + voiceChat gives echo cancellation and keeps running with the screen locked
 *  (UIBackgroundModes audio). Bluetooth HFP is what AirPods use for two-way audio. */
export async function configureAudioSession(): Promise<void> {
  if (sessionReady) return;
  AudioManager.setAudioSessionOptions({
    iosCategory: "playAndRecord",
    iosMode: "voiceChat",
    iosOptions: ["allowBluetoothHFP", "allowBluetoothA2DP", "defaultToSpeaker"],
  });
  AudioManager.observeAudioInterruptions(true);
  await AudioManager.setAudioSessionActivity(true);
  sessionReady = true;
}

/** After a phone call or Siri the session is deactivated; bring it back. */
export async function reactivateAudioSession(): Promise<void> {
  sessionReady = false;
  await configureAudioSession();
  if (ctx?.state === "suspended") await ctx.resume();
}

/** One context at the server's sample rate. Buffers at another rate are not resampled by
 *  the library (a 24 kHz Kokoro frame in a 48 kHz context plays at double speed), so the
 *  context is created lazily to match the first frame and rebuilt if the rate changes. */
function audioContext(sampleRate: number): AudioContext {
  if (ctx && ctx.sampleRate !== sampleRate) {
    clog(`audio context rate ${ctx.sampleRate} -> ${sampleRate}, recreating`);
    const old = ctx;
    ctx = null;
    void old.close();
  }
  if (!ctx) {
    ctx = new AudioContext({ sampleRate });
    clog(`audio context created @${ctx.sampleRate}, ${ctx.state}`);
  }
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

function setPlaying(on: boolean): void {
  if (reportedPlaying === on) return;
  reportedPlaying = on;
  send({ type: "playing", on });
}

/** A speak or permission_request event arrived. With a tts id, wait for its frames;
 *  without one and without a server voice, read it locally. */
export function hear(text: string, ttsId: number | undefined): void {
  const { voiceOn, serverTts } = useStore.getState();
  if (!voiceOn || !text) return;
  if (ttsId != null) {
    q.expect(ttsId);
    clog(`tts #${ttsId} expected, ${text.length} chars`);
  } else if (!serverTts) {
    Speech.speak(text);
  }
}

export function onAudioFrame(buf: ArrayBuffer): void {
  const { header, pcm } = parseAudioFrame(buf);
  if (!useStore.getState().voiceOn) return;
  const c = audioContext(header.sample_rate);
  const ab = c.createBuffer(1, pcm.length, header.sample_rate);
  const floats = new Float32Array(pcm.length);
  for (let i = 0; i < pcm.length; i++) floats[i] = pcm[i] / 32768;
  ab.copyToChannel(floats, 0);
  if (!q.push(header, ab)) {
    clog(`tts #${header.id} frame ${header.seq} ignored (cancelled)`);
    return;
  }
  clog(
    `tts #${header.id} frame ${header.seq}${header.last ? " (last)" : ""} received, ${(pcm.length / header.sample_rate).toFixed(2)}s, ctx ${c.state} @${c.sampleRate}, queue ${q.queue.length}, source ${source ? "busy" : "idle"}`,
  );
  if (!source) playNext();
}

function playNext(): void {
  const item = q.next();
  if (!item) {
    source = null;
    clog(`queue empty, ${q.active.size} tts still active`);
    if (!q.busy) setPlaying(false);
    return;
  }
  const c = audioContext(item.buffer.sampleRate);
  const src = c.createBufferSource();
  src.buffer = item.buffer;
  src.connect(c.destination);
  const started = Date.now();
  src.onEnded = () => {
    clog(
      `tts #${item.id} frame ${item.seq} ended after ${((Date.now() - started) / 1000).toFixed(2)}s of ${item.buffer.duration.toFixed(2)}s${source === src ? "" : " (stale)"}`,
    );
    if (source === src) playNext();
  };
  source = src;
  setPlaying(true);
  clog(`tts #${item.id} frame ${item.seq} playing, ctx ${c.state}`);
  src.start();
}

export function isSpeaking(): boolean {
  return q.busy;
}

/** Audio is coming out of the speaker right now. */
export function isPlaying(): boolean {
  return reportedPlaying;
}

export function stopSpeaking(reason: string): void {
  if (q.busy) clog(`stopSpeaking: ${reason}`);
  for (const id of q.clear()) send({ type: "tts_cancel", id });
  if (source) {
    const s = source;
    source = null;
    try {
      s.stop();
    } catch {
      // never started or already stopped
    }
  }
  void Speech.stop();
  setPlaying(false);
}

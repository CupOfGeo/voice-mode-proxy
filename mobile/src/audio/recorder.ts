/**
 * Speech in. Ported from the "microphone" block of web/index.html.
 *
 * Open mic, always on (REQUIREMENTS.md, Mic behaviour). The recorder delivers 100 ms of
 * 16 kHz mono float samples at a time; each chunk goes to the server as one PCM16 binary
 * frame. The server does voice activity detection and transcription. Echo cancellation
 * comes from the voiceChat audio session mode set in player.ts.
 */
import { AudioManager, AudioRecorder } from "react-native-audio-api";
import { clog, onOpen, send, sendBinary } from "../socket";
import { useStore } from "../store";
import { configureAudioSession, isPlaying, reactivateAudioSession, stopSpeaking } from "./player";

const SAMPLE_RATE = 16000;
const FRAME_SAMPLES = SAMPLE_RATE / 10; // 100 ms

let recorder: AudioRecorder | null = null;
let on = false;

export function isMicOn(): boolean {
  return on;
}

/** Float32 [-1, 1] to little-endian PCM16 bytes, the frame the server expects. */
export function floatsToPcm16(samples: Float32Array, count = samples.length): ArrayBuffer {
  const out = new Int16Array(count);
  for (let i = 0; i < count; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    out[i] = s < 0 ? s * 32768 : s * 32767;
  }
  return out.buffer;
}

export async function micOn(): Promise<void> {
  if (on) return;
  const { note } = useStore.getState();
  const permission = await AudioManager.requestRecordingPermissions();
  if (permission !== "Granted") {
    note("Mic permission denied. Allow the microphone for Voice Mode Proxy in Settings.");
    return;
  }
  await configureAudioSession();
  // stop() releases the native recorder, so every mic-on gets a fresh one.
  recorder?.clearOnAudioReady();
  recorder = new AudioRecorder();
  let frames = 0;
  recorder.onAudioReady({ sampleRate: SAMPLE_RATE, bufferLength: FRAME_SAMPLES, channelCount: 1 }, ({ buffer, numFrames }) => {
    if (!on) return;
    // Without hardware echo cancellation the speaker leaks into the mic, which reads as
    // you talking over the reply. Unless barge-in is on, hold the frames while audio plays.
    if (isPlaying() && !useStore.getState().bargeIn) return;
    frames++;
    if (frames === 1 || frames % 100 === 0) {
      clog(`mic frame ${frames}: ${numFrames} samples @${buffer.sampleRate}, ${buffer.numberOfChannels} ch`);
    }
    sendBinary(floatsToPcm16(buffer.getChannelData(0), numFrames));
  });
  const result = await recorder.start();
  if (result.status === "error") {
    note(`Mic failed: ${result.message}`);
    return;
  }
  on = true;
  useStore.getState().setMic(true);
  send({ type: "audio_start", sample_rate: SAMPLE_RATE });
  clog("mic on");
  note("Listening.");
}

export async function micOff(): Promise<void> {
  if (!on) return;
  on = false;
  useStore.getState().setMic(false);
  try {
    await recorder?.stop();
  } catch (e) {
    clog(`mic stop failed: ${e}`);
  }
  recorder?.clearOnAudioReady();
  recorder = null;
  send({ type: "audio_stop" });
  clog("mic off");
}

export function toggleMic(): void {
  void (on ? micOff() : micOn());
}

// The server forgets the mic pipeline when the socket drops; announce it again on reconnect.
onOpen(() => {
  if (on) send({ type: "audio_start", sample_rate: SAMPLE_RATE });
});

/**
 * Phone calls, Siri and alarms interrupt the audio session; pulling AirPods out changes
 * the route. Either can leave the recorder silent. Stop what we were saying, and once the
 * system says it is over, reactivate the session and restart the mic if it was on.
 * Step 6 of IOS-PLAN.md.
 */
let handlersInstalled = false;
export function installAudioSystemHandlers(): void {
  if (handlersInstalled) return;
  handlersInstalled = true;
  AudioManager.addSystemEventListener("interruption", (ev) => {
    clog(`audio interruption ${ev.type}${ev.shouldResume ? " (should resume)" : ""}, mic ${on ? "on" : "off"}`);
    if (ev.type === "began") {
      stopSpeaking("interruption");
      return;
    }
    setTimeout(() => void restartMicAfterSystemEvent("interruption ended"), 1000);
  });
  AudioManager.addSystemEventListener("routeChange", (ev) => {
    clog(`audio route change: ${ev.reason}, mic ${on ? "on" : "off"}`);
    if (ev.reason === "OldDeviceUnavailable" || ev.reason === "NewDeviceAvailable") {
      setTimeout(() => void restartMicAfterSystemEvent(`route ${ev.reason}`), 500);
    }
  });
}

async function restartMicAfterSystemEvent(why: string): Promise<void> {
  try {
    await reactivateAudioSession();
    if (!on) return;
    on = false; // micOn() is a no-op while on; drop the dead recorder and start a fresh one
    recorder?.clearOnAudioReady();
    recorder = null;
    await micOn();
    clog(`mic restarted after ${why}`);
  } catch (e) {
    clog(`mic restart after ${why} failed: ${e}`);
  }
}

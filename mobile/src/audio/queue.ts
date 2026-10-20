/**
 * Ordering and bookkeeping for spoken audio, with no native code, so it is unit tested.
 * Mirrors the `voice` object on the web page: which tts ids we are waiting for, the
 * frames queued to play, and which one is playing now.
 *
 * The server synthesises each spoken event once and streams one frame per sentence,
 * tagged with the event's tts id. Frames for ids we are not expecting (cancelled, or
 * from before this app connected) are dropped.
 */
import type { AudioFrameHeader } from "../protocol";

export interface QueuedFrame<B> {
  id: number;
  seq: number;
  last: boolean;
  buffer: B;
}

export class SpeechQueue<B> {
  /** tts ids announced by speak / permission_request events whose audio has not fully arrived. */
  readonly active = new Set<number>();
  readonly queue: QueuedFrame<B>[] = [];
  /** The frame playing now, or null. */
  playing: QueuedFrame<B> | null = null;

  expect(id: number): void {
    this.active.add(id);
  }

  /** Accept a decoded frame, or return false if it belongs to nothing we expect. */
  push(header: AudioFrameHeader, buffer: B): boolean {
    if (!this.active.has(header.id)) return false;
    this.queue.push({ id: header.id, seq: header.seq, last: header.last, buffer });
    return true;
  }

  /** Take the next frame to play; marks its id done when it is the last frame. */
  next(): QueuedFrame<B> | null {
    const item = this.queue.shift() ?? null;
    if (item?.last) this.active.delete(item.id);
    this.playing = item;
    return item;
  }

  /** Anything audible or still expected? Drives the "playing" gate sent to the server. */
  get busy(): boolean {
    return this.playing !== null || this.queue.length > 0 || this.active.size > 0;
  }

  /** Drop everything; returns the ids the server should stop synthesising. */
  clear(): number[] {
    const ids = [...this.active];
    this.active.clear();
    this.queue.length = 0;
    this.playing = null;
    return ids;
  }
}

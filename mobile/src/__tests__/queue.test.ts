import { SpeechQueue } from "../audio/queue";

const h = (id: number, seq: number, last = false) => ({ id, seq, last, sample_rate: 24000 });

describe("SpeechQueue", () => {
  it("drops frames for ids it is not expecting", () => {
    const q = new SpeechQueue<string>();
    expect(q.push(h(1, 0), "a")).toBe(false);
    expect(q.busy).toBe(false);
  });

  it("plays frames in arrival order and retires the id on the last frame", () => {
    const q = new SpeechQueue<string>();
    q.expect(1);
    expect(q.busy).toBe(true);
    q.push(h(1, 0), "a");
    q.push(h(1, 1, true), "b");
    expect(q.next()?.buffer).toBe("a");
    expect(q.active.has(1)).toBe(true);
    expect(q.next()?.buffer).toBe("b");
    expect(q.active.has(1)).toBe(false);
    expect(q.busy).toBe(true); // "b" is still playing
    expect(q.next()).toBeNull();
    expect(q.busy).toBe(false);
  });

  it("keeps two spoken events in order", () => {
    const q = new SpeechQueue<string>();
    q.expect(1);
    q.expect(2);
    q.push(h(1, 0, true), "one");
    q.push(h(2, 0, true), "two");
    expect([q.next()?.buffer, q.next()?.buffer]).toEqual(["one", "two"]);
  });

  it("clear returns the ids still being synthesised and empties everything", () => {
    const q = new SpeechQueue<string>();
    q.expect(3);
    q.expect(4);
    q.push(h(3, 0), "x");
    q.next();
    expect(q.clear().sort()).toEqual([3, 4]);
    expect(q.playing).toBeNull();
    expect(q.queue).toHaveLength(0);
    expect(q.busy).toBe(false);
    expect(q.push(h(3, 1, true), "late")).toBe(false);
  });
});

import { floatsToPcm16 } from "../audio/recorder";

// jest hoists these above the import
jest.mock("react-native-audio-api", () => ({ AudioManager: {}, AudioRecorder: jest.fn() }));
jest.mock("../socket", () => ({ clog: jest.fn(), onOpen: jest.fn(), send: jest.fn(), sendBinary: jest.fn() }));
jest.mock("../store", () => ({ useStore: { getState: () => ({}) } }));
jest.mock("../audio/player", () => ({ configureAudioSession: jest.fn() }));


describe("floatsToPcm16", () => {
  it("scales and clamps to 16-bit", () => {
    const out = new Int16Array(floatsToPcm16(new Float32Array([0, 1, -1, 0.5, 2, -2])));
    expect(Array.from(out)).toEqual([0, 32767, -32768, 16383, 32767, -32768]);
  });
  it("honours the frame count", () => {
    const out = new Int16Array(floatsToPcm16(new Float32Array([0.5, 0.5, 0.5, 0.5]), 2));
    expect(out.length).toBe(2);
  });
});

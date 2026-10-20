import { answered, initialState } from "../reducer";
import { EDIT_TOOLS, MODE_NEXT, formatDetail, modeLabel } from "../permission";
import type { PermissionRequest } from "../protocol";

describe("formatDetail", () => {
  it("commands, with and without a description", () => {
    expect(formatDetail({ command: "ls -la", description: "List files" })).toBe("ls -la\n\nList files");
    expect(formatDetail({ command: "ls", description: null })).toBe("ls");
  });
  it("edits as an old/new diff", () => {
    expect(formatDetail({ file: "a.py", edits: [{ old: "x", new: "y" }] })).toBe("a.py\n\n--- old\nx\n+++ new\ny");
  });
  it("writes as a byte count", () => {
    expect(formatDetail({ file: "b.py", bytes: 12 })).toBe("b.py\n12 bytes");
  });
  it("anything else as JSON", () => {
    expect(formatDetail({ url: "https://x" })).toBe('{\n  "url": "https://x"\n}');
    expect(formatDetail(null)).toBe("");
  });
});

describe("modes", () => {
  it("cycle auto -> acceptEdits -> default -> auto", () => {
    expect(MODE_NEXT[MODE_NEXT[MODE_NEXT.auto]]).toBe("auto");
    expect(modeLabel("acceptEdits")).toBe("accept edits");
    expect(modeLabel(undefined)).toBe("auto");
    expect(EDIT_TOOLS.has("Edit")).toBe(true);
    expect(EDIT_TOOLS.has("Bash")).toBe(false);
  });
});

describe("answered", () => {
  const req: PermissionRequest = { type: "permission_request", request_id: "r1", tool: "Bash", spoken: "run ls", detail: { command: "ls" } };
  it("drops the request and notes the answer", () => {
    const s = { ...initialState, pending: [req] };
    const out = answered(s, "r1", false);
    expect(out.pending).toEqual([]);
    expect(out.rows?.[0]).toMatchObject({ kind: "tool", text: "denied: run ls" });
  });
  it("ignores an unknown id", () => {
    expect(answered(initialState, "nope", true)).toEqual({});
  });
});

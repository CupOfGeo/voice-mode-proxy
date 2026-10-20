/** Pure helpers for the permission card and the mode button, mirrored from the page. */
import type { PermissionDetail, PermissionMode } from "./protocol";

export const EDIT_TOOLS = new Set(["Write", "Edit", "MultiEdit", "NotebookEdit"]);

export const MODE_LABEL: Record<PermissionMode, string> = {
  auto: "auto",
  acceptEdits: "accept edits",
  default: "ask for everything",
};

export const MODE_NEXT: Record<PermissionMode, PermissionMode> = {
  auto: "acceptEdits",
  acceptEdits: "default",
  default: "auto",
};

export function modeLabel(mode: string | undefined | null): string {
  return (mode && MODE_LABEL[mode as PermissionMode]) || mode || "auto";
}

/** The monospace block under the spoken line: command, edits, or file. */
export function formatDetail(d: PermissionDetail | null | undefined): string {
  if (!d) return "";
  if ("command" in d && typeof d.command === "string") {
    return d.command + (d.description ? `\n\n${d.description}` : "");
  }
  if ("edits" in d && Array.isArray(d.edits)) {
    return `${d.file}\n\n` + d.edits.map((e) => `--- old\n${e.old}\n+++ new\n${e.new}`).join("\n\n");
  }
  if ("file" in d && "bytes" in d) return `${d.file}\n${d.bytes} bytes`;
  return JSON.stringify(d, null, 2);
}

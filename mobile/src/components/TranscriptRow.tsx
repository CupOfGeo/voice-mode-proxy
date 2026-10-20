/** One line of the transcript, styled like the .msg / .speak / .tool / .heard rules on the page. */
import React from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { Text } from "react-native-paper";
import { formatDetail } from "../permission";
import type { PermissionDetail } from "../protocol";
import type { Row } from "../reducer";
import { palette } from "../theme";

function SpeakRow({ kind, text }: { kind: string; text: string }) {
  const tone =
    kind === "error"
      ? { backgroundColor: palette.errorBg, borderColor: palette.errorLine }
      : kind === "system"
        ? { backgroundColor: palette.panel2, borderColor: palette.line }
        : { backgroundColor: palette.speakBg, borderColor: palette.speakLine };
  return (
    <View style={[styles.speak, tone]}>
      <Text style={styles.kind}>{kind.toUpperCase()}</Text>
      <Text style={[styles.body, kind === "system" && { color: palette.muted }]}>{text}</Text>
    </View>
  );
}

/** A tool line; tap it to see the command, the diff or whatever else it was given. */
function ToolRow({ text, detail }: { text: string; detail?: PermissionDetail }) {
  const [open, setOpen] = React.useState(false);
  const body = formatDetail(detail);
  if (!body) return <Text style={styles.tool}>{text}</Text>;
  return (
    <View style={styles.toolBlock}>
      <Pressable onPress={() => setOpen(!open)} hitSlop={8}>
        <Text style={styles.tool}>
          {open ? "▾ " : "▸ "}
          {text}
        </Text>
      </Pressable>
      {open && (
        <Text style={styles.detail} selectable>
          {body}
        </Text>
      )}
    </View>
  );
}

export default React.memo(function TranscriptRow({ row }: { row: Row }) {
  switch (row.kind) {
    case "user":
      return (
        <View style={[styles.bubble, styles.user]}>
          <Text style={styles.body}>{row.text}</Text>
        </View>
      );
    case "assistant":
      return (
        <View style={[styles.bubble, styles.assistant]}>
          <Text style={[styles.body, styles.assistantText]}>{row.text}</Text>
        </View>
      );
    case "speak":
      return <SpeakRow kind={row.speakKind} text={row.text} />;
    case "tool":
      return <ToolRow text={row.text} detail={row.detail} />;
    case "heard":
      return <Text style={styles.heard}>🎤 {row.text}</Text>;
  }
});

const styles = StyleSheet.create({
  bubble: { maxWidth: "92%", paddingVertical: 9, paddingHorizontal: 12, borderRadius: 14 },
  user: { alignSelf: "flex-end", backgroundColor: palette.userBubble, borderBottomRightRadius: 4 },
  assistant: { alignSelf: "flex-start", backgroundColor: palette.panel2, borderBottomLeftRadius: 4 },
  assistantText: { color: "#c9cedb", fontSize: 15 },
  body: { color: palette.text, fontSize: 16, lineHeight: 22 },
  speak: { alignSelf: "stretch", borderWidth: 1, borderRadius: 10, paddingVertical: 9, paddingHorizontal: 12 },
  kind: { fontSize: 11, letterSpacing: 1, color: palette.muted, marginBottom: 3 },
  tool: { alignSelf: "flex-start", fontSize: 12, color: palette.muted, paddingHorizontal: 6 },
  toolBlock: { alignSelf: "stretch" },
  detail: {
    fontSize: 11,
    color: palette.text,
    fontFamily: "Menlo",
    backgroundColor: "#0f1218",
    borderRadius: 8,
    padding: 8,
    marginTop: 4,
  },
  heard: { alignSelf: "flex-end", fontSize: 12, color: palette.muted, paddingHorizontal: 6 },
});

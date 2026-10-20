import React from "react";
import { StyleSheet, View } from "react-native";
import { Text } from "react-native-paper";
import type { ConnState } from "../reducer";
import { palette } from "../theme";

const DOT: Record<ConnState, string> = { off: palette.bad, unpaired: palette.bad, idle: palette.ok, working: palette.warn };
const LABEL: Record<ConnState, string> = { off: "offline", unpaired: "unpaired", idle: "idle", working: "working" };

export default function StatusPill({ conn }: { conn: ConnState }) {
  return (
    <View style={styles.pill}>
      <View style={[styles.dot, { backgroundColor: DOT[conn] }]} />
      <Text style={styles.text}>{LABEL[conn]}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: palette.panel2,
    borderRadius: 999,
    paddingVertical: 3,
    paddingHorizontal: 9,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  text: { fontSize: 12, color: palette.muted },
});

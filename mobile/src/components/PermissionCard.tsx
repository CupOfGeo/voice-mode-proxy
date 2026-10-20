/**
 * The bottom card for the oldest pending permission request, mounted at the app root so
 * it shows over every screen. Tapping is the only way to answer; voice never is
 * (REQUIREMENTS.md, Permissions).
 */
import React from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Button, Text } from "react-native-paper";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useShallow } from "zustand/react/shallow";
import { EDIT_TOOLS, formatDetail } from "../permission";
import type { PermissionMode } from "../protocol";
import { send } from "../socket";
import { useStore } from "../store";
import { palette } from "../theme";

export default function PermissionCard() {
  const { pending, mode, answered } = useStore(
    useShallow((s) => ({ pending: s.pending, mode: s.session?.permission_mode, answered: s.answered })),
  );
  const insets = useSafeAreaInsets();
  const req = pending[0];
  if (!req) return null;

  const answer = (allow: boolean, newMode: PermissionMode | null = null) => {
    send({ type: "permission_response", request_id: req.request_id, allow, mode: newMode });
    answered(req.request_id, allow);
  };
  const offerEdits = EDIT_TOOLS.has(req.tool) && mode === "default";

  return (
    <View style={[styles.card, { paddingBottom: insets.bottom + 14 }]} pointerEvents="box-none">
      <Text style={styles.spoken}>{req.spoken}</Text>
      <Text style={styles.tool}>{req.tool}</Text>
      <ScrollView style={styles.detailBox} contentContainerStyle={styles.detailInner}>
        <Text style={styles.detail} selectable>
          {formatDetail(req.detail)}
        </Text>
      </ScrollView>
      <View style={styles.buttons}>
        <Button mode="contained" buttonColor="#3a3f4b" textColor={palette.text} style={styles.btn} onPress={() => answer(false)}>
          Deny
        </Button>
        {offerEdits && (
          <Button
            mode="contained"
            buttonColor={palette.userBubble}
            textColor="#fff"
            style={[styles.btn, styles.wide]}
            labelStyle={styles.smallLabel}
            onPress={() => answer(true, "acceptEdits")}
          >
            Allow edits this session
          </Button>
        )}
        <Button mode="contained" buttonColor={palette.ok} textColor="#062" style={styles.btn} onPress={() => answer(true)}>
          Allow
        </Button>
      </View>
      {pending.length > 1 && <Text style={styles.count}>{pending.length - 1} more waiting</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    padding: 14,
    backgroundColor: "#1c2230",
    borderTopWidth: 2,
    borderTopColor: palette.warn,
    shadowColor: "#000",
    shadowOpacity: 0.5,
    shadowRadius: 30,
    shadowOffset: { width: 0, height: -8 },
    elevation: 10,
  },
  spoken: { fontSize: 17, fontWeight: "600", color: palette.text, marginBottom: 6 },
  tool: { fontSize: 12, color: palette.muted, marginBottom: 8 },
  detailBox: { maxHeight: 220, backgroundColor: "#0f1218", borderRadius: 8, marginBottom: 12 },
  detailInner: { paddingVertical: 8, paddingHorizontal: 10 },
  detail: { fontSize: 12, color: palette.text, fontFamily: "Menlo" },
  buttons: { flexDirection: "row", gap: 8 },
  btn: { flex: 1, borderRadius: 10 },
  wide: { flex: 1.4 },
  smallLabel: { fontSize: 13 },
  count: { fontSize: 12, color: palette.muted, textAlign: "center", marginTop: 8 },
});

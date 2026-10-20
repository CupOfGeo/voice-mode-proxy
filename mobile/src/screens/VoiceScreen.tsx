/**
 * The main screen: status, session line, transcript, composer. Step 2 of IOS-PLAN.md.
 * Sessions and the permission card arrive in step 3, audio in steps 4 and 5.
 */
import React, { useCallback, useLayoutEffect, useMemo } from "react";
import { FlatList, KeyboardAvoidingView, Platform, StyleSheet, View } from "react-native";
import { useHeaderHeight } from "@react-navigation/elements";
import { Button, IconButton, Text } from "react-native-paper";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useShallow } from "zustand/react/shallow";
import Composer from "../components/Composer";
import StatusPill from "../components/StatusPill";
import TranscriptRow from "../components/TranscriptRow";
import type { RootScreenProps } from "../navigation/types";
import { MISMATCH_TEXT, UNPAIRED_TEXT } from "../protocol";
import type { Row } from "../reducer";
import { stopSpeaking } from "../audio/player";
import { toggleMic } from "../audio/recorder";
import { send } from "../socket";
import { useStore } from "../store";
import { palette } from "../theme";

const keyFor = (r: Row) => String(r.id);

export default function VoiceScreen({ navigation }: RootScreenProps<"Voice">) {
  const { conn, session, rows, micOn, speech, serverStt, mismatch } = useStore(
    useShallow((s) => ({
      conn: s.conn,
      session: s.session,
      rows: s.rows,
      micOn: s.micOn,
      speech: s.speech,
      serverStt: s.serverStt,
      mismatch: s.mismatch,
    })),
  );
  const headerHeight = useHeaderHeight();
  const insets = useSafeAreaInsets();

  const sessline = session ? `${session.project} · ${session.title || session.session_id.slice(0, 8)}` : "No session";

  useLayoutEffect(() => {
    navigation.setOptions({
      headerTitle: () => (
        <View>
          <Text style={styles.title}>Voice Mode Proxy</Text>
          <Text style={styles.sessline} numberOfLines={1}>
            {sessline}
          </Text>
        </View>
      ),
      headerRight: () => (
        <View style={styles.right}>
          <StatusPill conn={conn} />
          <IconButton icon="history" iconColor={palette.text} onPress={() => navigation.navigate("Sessions")} />
          <IconButton icon="cog-outline" iconColor={palette.text} onPress={() => navigation.navigate("Settings")} />
        </View>
      ),
    });
  }, [navigation, conn, sessline]);

  // Inverted list, the usual chat trick: the newest row is at index 0 and the list starts
  // and stays at the bottom, on first mount, on history replace, and on coming back from
  // another screen. No scrollToEnd bookkeeping.
  const newestFirst = useMemo(() => [...rows].reverse(), [rows]);

  const onSend = useCallback((text: string) => {
    stopSpeaking("typed text");
    send({ type: "user_text", text });
  }, []);
  const onStop = useCallback(() => {
    stopSpeaking("stop button");
    send({ type: "interrupt" });
  }, []);

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={headerHeight}
    >
      <FlatList
        data={newestFirst}
        inverted={rows.length > 0}
        keyExtractor={keyFor}
        renderItem={({ item }) => <TranscriptRow row={item} />}
        contentContainerStyle={styles.list}
        keyboardDismissMode="interactive"
        ListEmptyComponent={
          <Text style={styles.empty}>
            {conn === "off" ? "Connecting…" : conn === "unpaired" ? "Not paired." : serverStt ? "Tap the mic and talk, or type an instruction." : "Type an instruction."}
          </Text>
        }
      />
      <View style={{ paddingBottom: Math.max(insets.bottom, 10) - 2, backgroundColor: palette.panel }}>
        {mismatch ? (
          <Text style={styles.blocked}>{MISMATCH_TEXT[mismatch]}</Text>
        ) : conn === "unpaired" ? (
          <View style={styles.pairBox}>
            <Text style={styles.blocked}>{UNPAIRED_TEXT}</Text>
            <Button mode="contained" icon="link-variant" onPress={() => navigation.navigate("Pair")}>
              Pair this phone
            </Button>
          </View>
        ) : (
          <Composer
            working={conn === "working"}
            onSend={onSend}
            onStop={onStop}
            micOn={micOn}
            speech={speech}
            micEnabled={serverStt && conn !== "off"}
            onMic={toggleMic}
          />
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: palette.bg },
  title: { fontSize: 17, fontWeight: "600", color: palette.text },
  sessline: { fontSize: 12, color: palette.muted, maxWidth: 200 },
  right: { flexDirection: "row", alignItems: "center", gap: 4 },
  list: { padding: 14, gap: 8, flexGrow: 1 },
  empty: { color: palette.muted, textAlign: "center", marginTop: 40 },
  blocked: { color: palette.warn, textAlign: "center", padding: 14, fontSize: 14 },
  pairBox: { paddingHorizontal: 14, paddingBottom: 10, gap: 4 },
});

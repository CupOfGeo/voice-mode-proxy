/**
 * First run: the app opens here when no server URL is saved (phase two, step 3 of
 * IOS-PLAN.md). Each person runs their own proxy on their own Mac and reaches it over
 * their own Tailscale network; nothing here talks to anything George hosts.
 */
import React from "react";
import { Linking, ScrollView, StyleSheet, View } from "react-native";
import { Button, Text } from "react-native-paper";
import ServerUrlForm from "../components/ServerUrlForm";
import type { RootScreenProps } from "../navigation/types";
import { setDemoMode } from "../settings";
import { reconnect } from "../socket";
import { palette } from "../theme";

export const README_URL = "https://github.com/CupOfGeo/voice-mode-proxy#install-mac-with-apple-silicon";

const STEPS = [
  ["Install the server on your Mac.", "One command from the README. It needs Apple Silicon and about two gigabytes for the speech models."],
  ["Run it.", "vmp starts the proxy, loads the voice, and prints the address it is listening on."],
  ["Put Tailscale on this phone (recommended).", "Sign in to the same tailnet as the Mac. It keeps the proxy off the open internet: only your own devices can reach it, encrypted."],
  ["Paste the server address below.", "The Tailscale Serve address, for example https://mac.tail1234.ts.net:8443, or the Tailscale IP with the port. Then pair with a code from the Mac."],
];

export default function OnboardingScreen({ navigation }: RootScreenProps<"Onboarding">) {
  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled" automaticallyAdjustKeyboardInsets>
      <Text style={styles.title}>Talk to Claude Code from your pocket.</Text>
      <Text style={styles.lede}>
        This app is the voice in front of a proxy you run yourself. Four things to set up, once.
      </Text>
      {STEPS.map(([head, body], i) => (
        <View key={head} style={styles.step}>
          <Text style={styles.num}>{i + 1}</Text>
          <View style={styles.grow}>
            <Text style={styles.head}>{head}</Text>
            <Text style={styles.body}>{body}</Text>
          </View>
        </View>
      ))}
      <Button mode="text" icon="open-in-new" onPress={() => Linking.openURL(README_URL)} style={styles.readme}>
        Open the README
      </Button>
      <ServerUrlForm saveLabel="Continue" requireTest onSaved={() => navigation.replace("Pair")} />
      <Text style={styles.note}>
        No account. The next screen pairs this phone with a six-digit code from `vmp pair` on the Mac; that code is the
        only login. Tailscale keeps the proxy off the open internet.
      </Text>
      <Button
        mode="outlined"
        icon="play-circle-outline"
        style={styles.demo}
        onPress={async () => {
          await setDemoMode(true);
          reconnect();
          navigation.replace("Voice");
        }}
      >
        Try it without a server
      </Button>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, gap: 14, paddingBottom: 60 },
  title: { color: palette.text, fontSize: 24, fontWeight: "700" },
  lede: { color: palette.muted, fontSize: 15, marginBottom: 6 },
  step: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  num: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: palette.accent,
    color: "#0b1a33",
    fontWeight: "700",
    textAlign: "center",
    lineHeight: 26,
    overflow: "hidden",
  },
  grow: { flex: 1 },
  head: { color: palette.text, fontSize: 16, fontWeight: "600" },
  body: { color: palette.muted, fontSize: 14, lineHeight: 20 },
  readme: { alignSelf: "flex-start", marginLeft: -8 },
  note: { color: palette.muted, fontSize: 13, marginTop: 4 },
  demo: { marginTop: 8 },
});

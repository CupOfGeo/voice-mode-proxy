/**
 * Enter the six-digit code from `vmp pair` on the Mac. The server answers with a token
 * that goes in the keychain (settings.ts); from then on every socket and request carries
 * it. Reached from Onboarding after the URL test, from the Voice screen when the server
 * says "unpaired", and from Settings to pair again.
 */
import React, { useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Button, HelperText, Text, TextInput } from "react-native-paper";
import { pair } from "../api";
import type { RootScreenProps } from "../navigation/types";
import { reconnect } from "../socket";
import { useStore } from "../store";
import { palette } from "../theme";

export default function PairScreen({ navigation }: RootScreenProps<"Pair">) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("iPhone");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const digits = code.replace(/\D/g, "");

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const paired = await pair(digits, name.trim() || "iPhone");
      useStore.getState().note(`Paired as ${paired.name}.`);
      reconnect();
      if (navigation.canGoBack()) navigation.popToTop();
      else navigation.replace("Voice");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled" automaticallyAdjustKeyboardInsets>
      <Text style={styles.lede}>
        On the Mac, run <Text style={styles.code}>vmp pair</Text> and type the six digits it prints. A code lasts five
        minutes. The proxy must be running.
      </Text>
      <TextInput
        mode="outlined"
        label="Pairing code"
        value={code}
        onChangeText={(t) => {
          setCode(t);
          setError(null);
        }}
        keyboardType="number-pad"
        textContentType="oneTimeCode"
        maxLength={7}
        autoFocus
        placeholder="483 921"
      />
      <TextInput
        mode="outlined"
        label="This phone's name on the Mac"
        value={name}
        onChangeText={setName}
        autoCapitalize="words"
        placeholder="iPhone"
      />
      {error && (
        <HelperText type="error" visible>
          {error}
        </HelperText>
      )}
      <View style={styles.buttons}>
        <Button mode="contained" onPress={submit} loading={busy} disabled={busy || digits.length !== 6} style={styles.grow}>
          Pair
        </Button>
      </View>
      <Text style={styles.note}>
        The Mac keeps only a fingerprint of the key it gives this phone, under the name above. `vmp devices` lists paired phones and
        `vmp revoke` removes one.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, gap: 12, paddingBottom: 60 },
  lede: { color: palette.text, fontSize: 15, lineHeight: 22 },
  code: { fontFamily: "Menlo", color: palette.accent },
  buttons: { flexDirection: "row", gap: 8, marginTop: 4 },
  grow: { flex: 1 },
  note: { color: palette.muted, fontSize: 13, lineHeight: 18, marginTop: 6 },
});

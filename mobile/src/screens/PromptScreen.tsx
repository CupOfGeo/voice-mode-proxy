/**
 * The voice prompt, the text appended to Claude Code's own system prompt that tells it to
 * write for the ear. Saving stores it on the server for every later session; the SDK sets
 * the system prompt once per connect, so "save and restart" resumes the current session
 * in place to pick it up without losing the conversation.
 */
import React, { useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Button, Text, TextInput } from "react-native-paper";
import { useShallow } from "zustand/react/shallow";
import type { RootScreenProps } from "../navigation/types";
import { send } from "../socket";
import { useStore } from "../store";
import { palette } from "../theme";

export default function PromptScreen({ navigation }: RootScreenProps<"Prompt">) {
  const { settings, session, conn } = useStore(
    useShallow((s) => ({ settings: s.settings, session: s.session, conn: s.conn })),
  );
  const saved = settings?.values.voice_prompt;
  const fallback = settings?.defaults.voice_prompt;
  // Edits in progress; null shows the server's text, so a save (or a change from another
  // device) shows through once the draft is cleared.
  const [draft, setDraft] = useState<string | null>(null);
  const text = draft ?? saved ?? "";

  const clean = text.trim();
  const dirty = saved !== undefined && clean !== saved.trim();
  const isDefault = fallback !== undefined && clean === fallback.trim();
  const canRestart = !!session && conn !== "working";

  const save = () => {
    const ok = send({ type: "settings", values: { voice_prompt: clean } });
    if (ok) setDraft(null);
    return ok;
  };
  const saveAndRestart = () => {
    if (save() && send({ type: "session_restart" })) navigation.popToTop();
  };

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled" automaticallyAdjustKeyboardInsets>
      <Text style={styles.hint}>
        Added to Claude Code&apos;s own system prompt for every voice session. Saved text applies to new sessions;
        restarting resumes the current one with the new prompt and keeps the conversation.
      </Text>
      <TextInput
        mode="outlined"
        multiline
        value={text}
        onChangeText={setDraft}
        editable={saved !== undefined}
        placeholder={saved === undefined ? "Connect to the server to load the prompt." : undefined}
        autoCapitalize="sentences"
        style={styles.input}
        contentStyle={styles.inputText}
      />
      <View style={styles.buttons}>
        <Button mode="text" onPress={() => fallback !== undefined && setDraft(fallback)} disabled={isDefault || fallback === undefined}>
          Reset to default
        </Button>
        <Button mode="outlined" onPress={save} disabled={!dirty || !clean}>
          Save
        </Button>
      </View>
      <Button mode="contained" onPress={saveAndRestart} disabled={!clean || !canRestart}>
        {dirty ? "Save and restart session" : "Restart session with this prompt"}
      </Button>
      {!canRestart && (
        <Text style={styles.hint}>
          {session ? "Wait for Claude to finish before restarting." : "No session to restart; the prompt will be used by the next one."}
        </Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, gap: 12, paddingBottom: 60 },
  hint: { color: palette.muted, fontSize: 13 },
  input: { minHeight: 280 },
  inputText: { fontSize: 15, lineHeight: 21 },
  buttons: { flexDirection: "row", justifyContent: "space-between", gap: 10 },
});

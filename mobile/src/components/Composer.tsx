/** The footer: mic (step 5), text box, Send or Stop depending on whether Claude is working. */
import React, { useState } from "react";
import { StyleSheet, TextInput, View } from "react-native";
import { Button, IconButton } from "react-native-paper";
import { palette } from "../theme";

interface Props {
  working: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  micOn: boolean;
  /** The server hears speech right now; the button pulses like the page's .speech class. */
  speech: boolean;
  micEnabled: boolean;
  onMic: () => void;
}

export default function Composer({ working, onSend, onStop, micOn, speech, micEnabled, onMic }: Props) {
  const [text, setText] = useState("");
  const submit = () => {
    const t = text.trim();
    if (!t) return;
    onSend(t);
    setText("");
  };
  return (
    <View style={styles.bar}>
      <IconButton
        icon={micOn ? "microphone" : "microphone-outline"}
        iconColor={micOn ? palette.ok : palette.text}
        style={[styles.mic, micOn && styles.micOn, micOn && speech && styles.micSpeech]}
        disabled={!micEnabled}
        onPress={onMic}
        accessibilityLabel={micOn ? "Close mic" : "Open mic, always listening"}
      />
      <TextInput
        style={styles.input}
        value={text}
        onChangeText={setText}
        placeholder="Type an instruction…"
        placeholderTextColor={palette.muted}
        autoCapitalize="sentences"
        autoCorrect
        returnKeyType="send"
        onSubmitEditing={submit}
        blurOnSubmit={false}
      />
      {working ? (
        <Button mode="contained" buttonColor={palette.bad} textColor="#fff" onPress={onStop} style={styles.button}>
          Stop
        </Button>
      ) : (
        <Button mode="contained" onPress={submit} disabled={!text.trim()} style={styles.button}>
          Send
        </Button>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 10,
    paddingTop: 8,
    backgroundColor: palette.panel,
    borderTopWidth: 1,
    borderTopColor: palette.line,
  },
  mic: { margin: 0, borderWidth: 1, borderColor: palette.line, borderRadius: 10, backgroundColor: palette.panel2 },
  micOn: { borderColor: palette.ok },
  micSpeech: { backgroundColor: palette.speakBg },
  input: {
    flex: 1,
    fontSize: 16,
    color: palette.text,
    backgroundColor: palette.panel2,
    borderWidth: 1,
    borderColor: palette.line,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  button: { borderRadius: 10 },
});

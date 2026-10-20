/**
 * The server URL field with its Test connection check, shared by the first-run screen and
 * Settings. Test calls GET /health and shows the whisper and voice names it gets back, so
 * a user knows they are talking to the right thing; a protocol mismatch is reported in words.
 */
import React, { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";
import { Button, HelperText, TextInput } from "react-native-paper";
import { MISMATCH_TEXT, protocolMismatch } from "../protocol";
import { fetchHealth, getServerUrl, normalizeServerUrl, plainHttpProblem, setDemoMode, setServerUrl } from "../settings";
import { reconnect } from "../socket";
import { palette } from "../theme";

interface Props {
  saveLabel?: string;
  /** When true the save button waits for a successful test first. */
  requireTest?: boolean;
  onSaved: (url: string) => void;
}

export default function ServerUrlForm({ saveLabel = "Save URL", requireTest = false, onSaved }: Props) {
  const [url, setUrl] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    getServerUrl().then((u) => {
      setUrl(u);
      setLoaded(true);
    });
  }, []);

  const test = async () => {
    const clean = normalizeServerUrl(url);
    if (!clean) return;
    const problem = plainHttpProblem(clean);
    if (problem) {
      setResult({ ok: false, text: problem });
      return;
    }
    setChecking(true);
    setResult(null);
    try {
      const h = await fetchHealth(clean);
      const mismatch = protocolMismatch(h.protocol);
      if (mismatch) {
        setResult({ ok: false, text: MISMATCH_TEXT[mismatch] });
        return;
      }
      const parts = [
        h.whisper ? `whisper ${h.whisper.split("/").pop()}` : "no speech recognition",
        h.tts ? `voice ${h.tts}` : "no server voice",
      ];
      if (h.session !== undefined) parts.push(h.session ? `session in ${h.session.project}` : "no session"); // paired
      setResult({ ok: true, text: `Connected: ${parts.join(" · ")}` });
    } catch (e) {
      setResult({ ok: false, text: `Could not reach ${clean}: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setChecking(false);
    }
  };

  const save = async () => {
    const problem = plainHttpProblem(normalizeServerUrl(url));
    if (problem) {
      setResult({ ok: false, text: problem });
      return;
    }
    const clean = await setServerUrl(url);
    await setDemoMode(false); // saving a real server is how demo mode ends
    reconnect();
    onSaved(clean);
  };

  const canSave = loaded && !!url.trim() && (!requireTest || !!result?.ok);

  return (
    <View style={styles.form}>
      <TextInput
        mode="outlined"
        label="Server URL"
        value={url}
        onChangeText={(t) => {
          setUrl(t);
          setResult(null);
        }}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        textContentType="URL"
        editable={loaded}
        placeholder="https://host.tailnet.ts.net:8443"
      />
      {result && (
        <HelperText type={result.ok ? "info" : "error"} visible style={result.ok ? styles.okText : undefined}>
          {result.text}
        </HelperText>
      )}
      <View style={styles.buttons}>
        <Button mode="outlined" onPress={test} loading={checking} disabled={checking || !url.trim()} style={styles.grow}>
          Test connection
        </Button>
        <Button mode="contained" onPress={save} disabled={!canSave} style={styles.grow}>
          {saveLabel}
        </Button>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  form: { gap: 8 },
  buttons: { flexDirection: "row", gap: 8 },
  grow: { flex: 1 },
  okText: { color: palette.ok },
});

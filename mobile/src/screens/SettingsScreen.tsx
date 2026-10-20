/**
 * Where the server lives, plus the controls that used to sit on the sessions screen.
 * Permission mode, speed, the listening timings and the voice go through the server,
 * which echoes the new values to every client; the phone keeps nothing of its own
 * except the URL. "Speak replies" and barge-in are phone-side, in memory like the page.
 */
import Slider from "@react-native-community/slider";
import React, { useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Button, Divider, List, Menu, SegmentedButtons, Switch, Text } from "react-native-paper";
import { useShallow } from "zustand/react/shallow";
import ServerUrlForm from "../components/ServerUrlForm";
import type { RootScreenProps } from "../navigation/types";
import { MODE_LABEL } from "../permission";
import type { PermissionMode, SettingsValues } from "../protocol";
import { clearToken } from "../settings";
import { reconnect, send } from "../socket";
import { useStore } from "../store";
import { palette } from "../theme";

const MODES: PermissionMode[] = ["auto", "acceptEdits", "default"];
const ms = (x: number) => `${(x / 1000).toFixed(1)} s`;
const round2 = (x: number) => Math.round(x * 100) / 100;

interface SliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (x: number) => string;
  disabled?: boolean;
  /** Called once when the thumb is released, not on every tick. */
  onCommit: (x: number) => void;
}

function TunableSlider({ label, value, min, max, step, format, disabled, onCommit }: SliderProps) {
  // The number shown while the thumb is moving; null when the server's value is current.
  const [dragging, setDragging] = useState<number | null>(null);
  return (
    <View style={styles.block}>
      <View style={styles.rowBetween}>
        <Text style={styles.label}>{label}</Text>
        <Text style={styles.value}>{format(dragging ?? value)}</Text>
      </View>
      <Slider
        minimumValue={min}
        maximumValue={max}
        step={step}
        value={value}
        disabled={disabled}
        onValueChange={setDragging}
        onSlidingComplete={(x) => {
          setDragging(null);
          onCommit(x);
        }}
        minimumTrackTintColor={palette.accent}
        maximumTrackTintColor={palette.line}
        thumbTintColor={palette.accent}
      />
    </View>
  );
}

function ToggleRow({ label, hint, value, onChange }: { label: string; hint: string; value: boolean; onChange: (on: boolean) => void }) {
  return (
    <View style={styles.rowBetween}>
      <View style={styles.grow}>
        <Text style={styles.label}>{label}</Text>
        <Text style={styles.hint}>{hint}</Text>
      </View>
      <Switch value={value} onValueChange={onChange} color={palette.accent} />
    </View>
  );
}

export default function SettingsScreen({ navigation }: RootScreenProps<"Settings">) {
  const { session, settings, serverStt, serverTts, voiceOn, bargeIn, setVoice, setBargeIn } = useStore(
    useShallow((s) => ({
      session: s.session,
      settings: s.settings,
      serverStt: s.serverStt,
      serverTts: s.serverTts,
      voiceOn: s.voiceOn,
      bargeIn: s.bargeIn,
      setVoice: s.setVoice,
      setBargeIn: s.setBargeIn,
    })),
  );
  const [advanced, setAdvanced] = useState(false);
  const [voiceMenu, setVoiceMenu] = useState(false);

  const change = (values: Partial<SettingsValues>) => send({ type: "settings", values });
  const v = settings?.values;
  const d = settings?.defaults;

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled" automaticallyAdjustKeyboardInsets>
      <List.Subheader style={styles.subheader}>Server</List.Subheader>
      <Text style={styles.hint}>
        The proxy running on your Mac, usually over Tailscale. Use the Tailscale Serve address, for example
        https://mac.tail1234.ts.net:8443, or the Tailscale IP with the port.
      </Text>
      <ServerUrlForm onSaved={() => navigation.goBack()} />
      <View style={styles.row}>
        <Button mode="outlined" icon="link-variant" onPress={() => navigation.navigate("Pair")} style={styles.grow}>
          Pair again
        </Button>
        <Button
          mode="outlined"
          icon="link-variant-off"
          onPress={async () => {
            await clearToken();
            reconnect();
          }}
          style={styles.grow}
        >
          Unpair this phone
        </Button>
      </View>
      <Text style={styles.hint}>
        Pairing is per server. On the Mac, `vmp devices` lists paired phones and `vmp revoke &lt;name&gt;` removes one.
      </Text>

      <Divider style={styles.divider} />
      <List.Subheader style={styles.subheader}>Session</List.Subheader>
      <Text style={styles.label}>Permission mode</Text>
      <SegmentedButtons
        value={session?.permission_mode ?? "auto"}
        onValueChange={(m) => send({ type: "permission_mode", mode: m as PermissionMode })}
        buttons={MODES.map((m) => ({ value: m, label: MODE_LABEL[m], disabled: !session }))}
      />
      <Text style={styles.hint}>
        {session ? "Changes the running session. New sessions start in the server's default mode." : "No session running; new sessions start in the server's default mode."}
      </Text>
      <ToggleRow label="Speak replies" hint="Read replies aloud on this phone." value={voiceOn} onChange={setVoice} />
      <ToggleRow
        label="Barge-in"
        hint="Keep the mic open while a reply plays so you can talk over it. Off with the phone speaker, or it hears itself."
        value={bargeIn}
        onChange={setBargeIn}
      />

      <Divider style={styles.divider} />
      <List.Subheader style={styles.subheader}>Speech</List.Subheader>
      {v && d ? (
        <>
          <TunableSlider
            label="Speed"
            value={v.speech_rate}
            min={0.5}
            max={2}
            step={0.05}
            format={(x) => `${x.toFixed(2)}×`}
            disabled={!serverTts}
            onCommit={(x) => change({ speech_rate: round2(x) })}
          />
          <Button mode="outlined" icon="text-box-edit-outline" onPress={() => navigation.navigate("Prompt")}>
            Edit voice prompt
          </Button>
          <List.Accordion
            title="Advanced"
            expanded={advanced}
            onPress={() => setAdvanced(!advanced)}
            style={styles.accordion}
            titleStyle={styles.label}
          >
            <TunableSlider
              label="Pause that ends what you said"
              value={v.vad_silence_ms}
              min={300}
              max={5000}
              step={100}
              format={ms}
              disabled={!serverStt}
              onCommit={(x) => change({ vad_silence_ms: Math.round(x) })}
            />
            <TunableSlider
              label="Shortest sound that counts"
              value={v.vad_min_speech_ms}
              min={0}
              max={2000}
              step={50}
              format={ms}
              disabled={!serverStt}
              onCommit={(x) => change({ vad_min_speech_ms: Math.round(x) })}
            />
            <TunableSlider
              label="Speech needed to interrupt a reply"
              value={v.vad_barge_in_ms}
              min={0}
              max={5000}
              step={100}
              format={ms}
              disabled={!serverStt}
              onCommit={(x) => change({ vad_barge_in_ms: Math.round(x) })}
            />
            <View style={[styles.rowBetween, styles.block]}>
              <Text style={styles.label}>Voice</Text>
              <Menu
                visible={voiceMenu}
                onDismiss={() => setVoiceMenu(false)}
                anchor={
                  <Button mode="outlined" compact onPress={() => setVoiceMenu(true)} disabled={!settings.voices.length}>
                    {v.kokoro_voice}
                  </Button>
                }
              >
                <ScrollView style={styles.menu}>
                  {settings.voices.map((name) => (
                    <Menu.Item
                      key={name}
                      title={name}
                      trailingIcon={name === v.kokoro_voice ? "check" : undefined}
                      onPress={() => {
                        setVoiceMenu(false);
                        if (name !== v.kokoro_voice) change({ kokoro_voice: name });
                      }}
                    />
                  ))}
                </ScrollView>
              </Menu>
            </View>
            <Button
              mode="text"
              onPress={() =>
                change({
                  speech_rate: d.speech_rate,
                  kokoro_voice: d.kokoro_voice,
                  vad_silence_ms: d.vad_silence_ms,
                  vad_min_speech_ms: d.vad_min_speech_ms,
                  vad_barge_in_ms: d.vad_barge_in_ms,
                })
              }
            >
              Reset speech settings to the server defaults
            </Button>
          </List.Accordion>
        </>
      ) : (
        <Text style={styles.hint}>Connect to the server to see its speech settings.</Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, paddingTop: 8, gap: 12, paddingBottom: 60 },
  subheader: { color: palette.muted, paddingHorizontal: 0 },
  divider: { marginVertical: 8, backgroundColor: palette.line },
  label: { color: palette.text, fontSize: 15 },
  value: { color: palette.muted, fontVariant: ["tabular-nums"] },
  hint: { color: palette.muted, fontSize: 13 },
  okText: { color: palette.ok },
  buttons: { flexDirection: "row", gap: 10 },
  grow: { flex: 1 },
  row: { flexDirection: "row", gap: 8, marginTop: 8 },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  block: { gap: 2 },
  accordion: { backgroundColor: palette.panel, paddingHorizontal: 0 },
  menu: { maxHeight: 320 },
});

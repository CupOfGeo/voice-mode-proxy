/**
 * The sessions panel from the page as its own screen: the current session, every
 * project you can start a session in, and recent sessions to resume. The mode, voice
 * and barge-in controls that sat here live on the Settings screen now.
 */
import React, { useCallback, useState } from "react";
import { SectionList, Share, StyleSheet, View } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { Button, List, Text } from "react-native-paper";
import { useShallow } from "zustand/react/shallow";
import { fetchSessions, sessionLink } from "../api";
import type { RootScreenProps } from "../navigation/types";
import { modeLabel } from "../permission";
import type { Project, SessionSummary } from "../protocol";
import { send } from "../socket";
import { useStore } from "../store";
import { palette } from "../theme";

type Item = { kind: "project"; project: Project } | { kind: "recent"; row: SessionSummary };

function recentLabel(r: SessionSummary): string {
  const folder = (r.cwd || "").split("/").pop() || "";
  const when = (r.updated || "").slice(0, 16).replace("T", " ");
  return `${folder} · ${when} · ${r.title || r.first_prompt || ""}`;
}

export default function SessionsScreen({ navigation }: RootScreenProps<"Sessions">) {
  const { session, projects, note } = useStore(
    useShallow((s) => ({ session: s.session, projects: s.projects, note: s.note })),
  );
  const [recent, setRecent] = useState<SessionSummary[] | null>(null);
  const [recentError, setRecentError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      fetchSessions()
        .then((rows) => {
          if (!cancelled) setRecent(rows);
        })
        .catch((e) => {
          if (!cancelled) setRecentError(e instanceof Error ? e.message : String(e));
        });
      return () => {
        cancelled = true;
      };
    }, []),
  );

  const newSession = (p: Project) => {
    if (send({ type: "session_new", cwd: p.path })) navigation.goBack();
  };
  const resume = (r: SessionSummary) => {
    if (send({ type: "session_resume", session_id: r.session_id })) navigation.goBack();
  };
  const share = async () => {
    if (!session) {
      note("No session to link yet.");
      return;
    }
    await Share.share({ url: await sessionLink(session.session_id) });
  };

  const sections = [
    { title: "New session in…", data: projects.map((project): Item => ({ kind: "project", project })) },
    { title: "Recent", data: (recent ?? []).map((row): Item => ({ kind: "recent", row })) },
  ];

  return (
    <SectionList
      sections={sections}
      keyExtractor={(it) => (it.kind === "project" ? `p:${it.project.path}` : `r:${it.row.session_id}`)}
      stickySectionHeadersEnabled={false}
      contentContainerStyle={styles.list}
      ListHeaderComponent={
        <View style={styles.current}>
          <Text style={styles.currentText}>
            {session
              ? `${session.project} · ${session.title || session.session_id.slice(0, 8)} · ${session.model || "starting"} · ${modeLabel(session.permission_mode)}`
              : "No session."}
          </Text>
          <View style={styles.row}>
            <Button mode="outlined" compact onPress={share} icon="share-variant" disabled={!session}>
              Share link
            </Button>
            <Button mode="outlined" compact onPress={() => send({ type: "projects_reload" })} icon="refresh">
              Rescan
            </Button>
          </View>
        </View>
      }
      renderSectionHeader={({ section }) => <List.Subheader style={styles.subheader}>{section.title}</List.Subheader>}
      renderItem={({ item }) =>
        item.kind === "project" ? (
          <List.Item title={item.project.name} description={item.project.path} onPress={() => newSession(item.project)} titleStyle={styles.itemTitle} descriptionStyle={styles.itemDesc} left={(p) => <List.Icon {...p} icon="folder-outline" color={palette.muted} />} />
        ) : (
          <List.Item title={recentLabel(item.row)} titleNumberOfLines={2} onPress={() => resume(item.row)} titleStyle={styles.itemTitle} right={(p) => <List.Icon {...p} icon="play-outline" color={palette.accent} />} />
        )
      }
      renderSectionFooter={({ section }) =>
        section.title === "Recent" && !section.data.length ? (
          <Text style={styles.emptyText}>{recentError ? `Could not load sessions: ${recentError}` : recent === null ? "Loading…" : "No past sessions."}</Text>
        ) : null
      }
    />
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 40 },
  current: { padding: 14, backgroundColor: palette.panel, borderBottomWidth: 1, borderBottomColor: palette.line },
  currentText: { fontSize: 13, color: palette.muted, marginBottom: 10 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  subheader: { color: palette.muted },
  itemTitle: { color: palette.text, fontSize: 15 },
  itemDesc: { color: palette.muted, fontSize: 12 },
  emptyText: { color: palette.muted, paddingHorizontal: 16, paddingVertical: 8 },
});

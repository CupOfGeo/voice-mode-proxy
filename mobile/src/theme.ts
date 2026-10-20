/** The web page's palette (web/index.html :root), on top of Paper's MD3 dark theme. */
import { MD3DarkTheme } from "react-native-paper";

export const palette = {
  bg: "#111318",
  panel: "#1a1d24",
  panel2: "#22262f",
  line: "#2c313c",
  text: "#e8eaf0",
  muted: "#8b93a5",
  accent: "#6ea8fe",
  ok: "#3ddc84",
  bad: "#ff6b6b",
  warn: "#ffb454",
  userBubble: "#2b4a7a",
  speakBg: "#1f3524",
  speakLine: "#2f5c3a",
  errorBg: "#3a2020",
  errorLine: "#6b2f2f",
} as const;

export const theme = {
  ...MD3DarkTheme,
  colors: {
    ...MD3DarkTheme.colors,
    primary: palette.accent,
    onPrimary: "#0b1a33",
    background: palette.bg,
    onBackground: palette.text,
    surface: palette.panel,
    onSurface: palette.text,
    surfaceVariant: palette.panel2,
    onSurfaceVariant: palette.muted,
    outline: palette.line,
    outlineVariant: palette.line,
    error: palette.bad,
    elevation: {
      ...MD3DarkTheme.colors.elevation,
      level0: palette.bg,
      level1: palette.panel,
      level2: palette.panel2,
      level3: palette.panel2,
    },
  },
};

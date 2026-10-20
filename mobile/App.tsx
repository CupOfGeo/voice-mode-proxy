import React, { useEffect, useState } from "react";
import { NavigationContainer, DarkTheme as NavDarkTheme } from "@react-navigation/native";
import { PaperProvider } from "react-native-paper";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import PermissionCard from "./src/components/PermissionCard";
import RootNavigator from "./src/navigation/RootNavigator";
import { configureAudioSession, onAudioFrame } from "./src/audio/player";
import { installAudioSystemHandlers } from "./src/audio/recorder";
import { getDemoMode, getServerUrl, getToken } from "./src/settings";
import { setBinaryHandler, startSocket } from "./src/socket";
import { palette, theme } from "./src/theme";

const navTheme = {
  ...NavDarkTheme,
  colors: { ...NavDarkTheme.colors, background: palette.bg, card: palette.panel, text: palette.text, border: palette.line, primary: palette.accent },
};

export default function App() {
  // Onboarding until a server URL is saved, then Pair until a token is; demo mode skips both.
  // Null while the saved values are being read.
  const [initialRoute, setInitialRoute] = useState<"Onboarding" | "Pair" | "Voice" | null>(null);
  useEffect(() => {
    Promise.all([getServerUrl(), getDemoMode(), getToken()]).then(([u, d, t]) =>
      setInitialRoute(d ? "Voice" : u && t ? "Voice" : u ? "Pair" : "Onboarding"),
    );
  }, []);
  useEffect(() => {
    setBinaryHandler(onAudioFrame);
    configureAudioSession()
      .then(installAudioSystemHandlers)
      .catch((e) => console.warn("audio session", e));
    startSocket();
  }, []);
  if (!initialRoute) return null;
  return (
    <SafeAreaProvider>
      <PaperProvider theme={theme}>
        <NavigationContainer theme={navTheme}>
          <RootNavigator initialRoute={initialRoute} />
        </NavigationContainer>
        <PermissionCard />
        <StatusBar style="light" />
      </PaperProvider>
    </SafeAreaProvider>
  );
}

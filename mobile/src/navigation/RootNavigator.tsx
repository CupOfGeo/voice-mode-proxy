import React from "react";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import OnboardingScreen from "../screens/OnboardingScreen";
import PairScreen from "../screens/PairScreen";
import VoiceScreen from "../screens/VoiceScreen";
import SessionsScreen from "../screens/SessionsScreen";
import SettingsScreen from "../screens/SettingsScreen";
import PromptScreen from "../screens/PromptScreen";
import { palette } from "../theme";
import type { RootParamList } from "./types";

const Stack = createNativeStackNavigator<RootParamList>();

export default function RootNavigator({ initialRoute }: { initialRoute: keyof RootParamList }) {
  return (
    <Stack.Navigator
      initialRouteName={initialRoute}
      screenOptions={{
        headerStyle: { backgroundColor: palette.panel },
        headerTintColor: palette.text,
        headerShadowVisible: false,
        contentStyle: { backgroundColor: palette.bg },
      }}
    >
      <Stack.Screen name="Onboarding" component={OnboardingScreen} options={{ title: "Set up", headerBackVisible: false }} />
      <Stack.Screen name="Pair" component={PairScreen} options={{ title: "Pair this phone" }} />
      <Stack.Screen name="Voice" component={VoiceScreen} options={{ title: "Voice Mode Proxy" }} />
      <Stack.Screen name="Sessions" component={SessionsScreen} options={{ title: "Sessions" }} />
      <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: "Settings" }} />
      <Stack.Screen name="Prompt" component={PromptScreen} options={{ title: "Voice prompt" }} />
    </Stack.Navigator>
  );
}

import type { NativeStackScreenProps } from "@react-navigation/native-stack";

export type RootParamList = {
  Onboarding: undefined;
  Pair: undefined;
  Voice: undefined;
  Settings: undefined;
  Sessions: undefined;
  Prompt: undefined;
};

export type RootScreenProps<T extends keyof RootParamList> = NativeStackScreenProps<RootParamList, T>;

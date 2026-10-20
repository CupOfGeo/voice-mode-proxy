// react-native-audio-api's index exports an AudioControls scrubber that imports
// react-native-gesture-handler and react-native-reanimated, neither of which is a declared
// peer dependency and neither of which this app uses. Point both at an empty module so the
// bundle resolves without adding two native packages.
const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);
const STUBBED = new Set(["react-native-gesture-handler", "react-native-reanimated"]);
const base = config.resolver.resolveRequest;

config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (STUBBED.has(moduleName)) return { type: "sourceFile", filePath: require.resolve("./stubs/empty.js") };
  return base ? base(context, moduleName, platform) : context.resolveRequest(context, moduleName, platform);
};

module.exports = config;

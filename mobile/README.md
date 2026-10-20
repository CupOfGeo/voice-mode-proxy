# Voice Mode Proxy — iOS app

Expo + React Native client for the proxy in the parent folder. See `../IOS-PLAN.md` for
the build order and decisions. Runs as a dev client on a physical iPhone; the simulator
has no real microphone or background audio.

## First time

```bash
cd mobile
npm install
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer   # once, if Xcode is not active
```

Plug the phone in, unlock it, trust the Mac, and turn on Developer Mode
(Settings → Privacy & Security → Developer Mode). Then:

```bash
npm run ios          # expo run:ios --device: builds and installs the dev client
```

On the phone, trust the developer profile under Settings → General → VPN & Device
Management. Open the app, tap the cog, enter the server URL (the Tailscale Serve address,
e.g. `https://mac.tail1234.ts.net:8443`), tap Test connection, Save. Then run `uv run vmp pair`
on the Mac and type the six digits on the Pair screen; the token lands in the phone keychain
(`expo-secure-store`, a native module, so a dev client from before 2026-09-23 needs `npm run ios`).

## Gotchas

- **Xcode 27 requires the UIScene lifecycle.** Without it the app dies at launch with
  SIGTRAP before any JS runs. `app.json` opts in through `expo-build-properties`
  (`ios.enableSceneSupport: true`), which needs `expo` 57.0.23 or newer. Do not remove it
  until the app is on SDK 58, where it is the default.
- **npm's `min-release-age` (7 days on this Mac) can hide the Expo patch you need.** Override
  for one command with `npm install <pkg>@<version> --min-release-age=0`.
- **`appleTeamId` in `app.json`** keeps signing working across `expo prebuild --clean`, which
  otherwise wipes the team chosen in Xcode.
- **A fresh certificate makes codesign ask for the keychain password once per framework.**
  Stop the build, then run
  `security set-key-partition-list -S apple-tool:,apple:,codesign: -s ~/Library/Keychains/login.keychain-db`
  and rebuild. If the prompts will not close, `killall -9 SecurityAgent`.
- **`metro.config.js` stubs `react-native-gesture-handler` and `react-native-reanimated`.**
  `react-native-audio-api` re-exports a scrubber UI that imports both; the app never
  renders it. If a future need for either package arises, install them properly and
  delete the stub. Metro must be restarted after the config changes.
- **`@react-native-community/slider` is a native module.** Adding it (settings sliders)
  meant `npm run ios` again; a JS-only reload shows a blank slider. Same for any future
  native dependency: `npx expo install <pkg>`, then rebuild.
- **Pull a crash report from the phone** with `uvx pymobiledevice3 crash pull <dir>`; the
  `.ips` files are JSON after the first line.

## Using it

Tap the mic once; it stays on. Lock the phone and put it in a pocket: the audio session keeps
the app alive, so the socket, mic and speaker all keep working with the screen off. While a
reply plays the mic holds its frames (no hardware echo cancellation yet), so wait for the
reply to finish or press Stop. Turn barge-in on from the Sessions screen if you would rather
talk over replies and accept some echo. Permission requests appear as a card and must be
tapped; the mic never answers them. The session log on the server records every app state
change, mic frame count, interruption and route change under `client` events.

## Day to day

```bash
npm start            # expo start --dev-client; scan the QR code with the Camera app
```

JS changes hot-reload. Rebuild with `npm run ios` only after adding a native package or
changing `app.json`.

## Leaving the house

A dev-client build loads its JavaScript from Metro on the Mac. Once loaded it keeps running
off WiFi (the proxy is reached over Tailscale, not Metro), but if iOS kills the app while
you are out it cannot reload from a LAN address. Either:

- In the dev launcher, enter Metro by the Mac's Tailscale name, e.g.
  `http://<your-mac>.<your-tailnet>.ts.net:8081`, instead of the `192.168.x.x` address.
  Metro listens on every interface, so this works from anywhere on the tailnet.
- Or build once with the bundle embedded, which needs no Metro at all:
  `npx expo run:ios --device --configuration Release`. Rebuild after every JS change.
  Over WiFi the install step can sit at "Connecting to" forever after "Build Succeeded"
  (2026-09-22, 17 minutes). Ctrl-C it and install the built app directly:
  `xcrun devicectl device install app --device <udid> ~/Library/Developer/Xcode/DerivedData/VoiceModeProxy-*/Build/Products/Release-iphoneos/VoiceModeProxy.app`
  (`xcrun devicectl list devices` shows the udid). Takes seconds.

## TestFlight

TestFlight is Apple's beta channel: you upload a build to App Store Connect, Apple processes
it, and testers install it through the TestFlight app. Two kinds of tester:

- **Internal** (up to 100 people you add to your App Store Connect team): no review, the
  build is available minutes after processing. This is how George tests release builds.
- **External** (anyone, by email or public link, up to 10,000): the first build of each
  version goes through a light App Review, usually a day. The reviewer has no server, so
  the review notes say "turn on demo mode".

Nothing runs on George's machines for testers; each person installs their own server.

### One-time setup
1. `eas init` has linked this folder to the Expo project (`extra.eas.projectId` in app.json).
2. In App Store Connect (https://appstoreconnect.apple.com) create the app record: name
   "Voice Mode Proxy", bundle id `net.mainbranch.voicemodeproxy`, category Developer Tools.
   `eas submit` can create it too, but doing it by hand shows every field.
3. App Privacy: microphone, used for app functionality, not linked to identity; no
   analytics, no tracking. Export compliance is already answered by
   `ITSAppUsesNonExemptEncryption: false` in app.json.

### Every build
```bash
npm run typecheck && npm run lint && npm test
eas build --profile production --platform ios   # signs in the cloud, ~15 min
eas submit --platform ios --latest              # uploads to App Store Connect
```
`eas build` asks for the Apple ID the first time and creates the distribution certificate
and provisioning profile itself; it stores them on EAS. The build number auto-increments
(`appVersionSource: remote`); bump `version` in app.json for a new marketing version.

After processing (10 to 30 minutes, an email arrives), the build shows under TestFlight in
App Store Connect. Add yourself as an internal tester once; every later build is offered
in the TestFlight app on the phone automatically.

## Checks

```bash
npm run typecheck
npm run lint
npm test
```

## Smoke test without the phone

With the proxy running on this Mac:

```bash
node scripts/smoke.mts                      # local server
node scripts/smoke.mts wss://host:8443/ws   # or any other
```

It listens for three seconds and prints what the app's reducer made of the hello,
history and any live events. It never sends anything.

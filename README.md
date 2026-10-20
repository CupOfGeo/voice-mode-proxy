# Voice Mode Proxy

A voice layer in front of Claude Code. Open the app on your phone, talk, and hear
short spoken replies instead of raw terminal output. The server runs at home, is reached
over Tailscale, and talks only to phones you have paired.

- **Client**: `web/index.html`, a single page that captures the mic (16 kHz PCM) and plays audio frames.
- **Server**: FastAPI + WebSocket in `voice_mode_proxy/server.py`.
- **Speech in**: Silero VAD + mlx-whisper (`speech.py`).
- **Agent**: Claude Code through the Agent SDK (`agent.py`), with a prompt that asks it to write for speech.
- **Speech out**: Kokoro (`tts.py`), streamed per sentence.
- **Sessions**: one JSON Lines log per session under `logs/`; resume from the phone.

## Install (Mac with Apple Silicon)

```sh
git clone https://github.com/CupOfGeo/voice-mode-proxy.git
cd voice-mode-proxy && ./install.sh
```

The script installs uv, the Python packages, the Kokoro voice files and the Whisper model,
writes a starter config, and checks for Claude Code and Tailscale (it tells you how to get
either if missing). Run it again any time; it skips what is already there.

## Run

```sh
uv run vmp start
```

That installs the proxy as a launchd agent, so it stays up across crashes and logins, and
starts it. The proxy listens on `127.0.0.1:8791` and refuses to start with a plain message
if Claude Code or the voice files are missing. Day to day:

```sh
uv run vmp status     # up? what /health says
uv run vmp logs       # follow logs/server.log
uv run vmp restart    # after git pull, or a changed config.toml
uv run vmp stop       # stays stopped until the next start
```

Plain `uv run vmp` runs it in the terminal instead, for hacking on it. Publish it on your
tailnet once per Mac:

```sh
tailscale serve --bg --https=8443 http://127.0.0.1:8791
```

Then paste `https://<this-mac>.<your-tailnet>.ts.net:8443` into the app's Settings screen
(`tailscale serve status` prints it). The old web page is still served at that URL as a fallback.

### Pair your phone

Only paired devices can use the proxy. `vmp start` prints a six-digit code the first time;
later, ask for one any time:

```sh
uv run vmp pair                    # prints a code, good for 5 minutes and 5 tries
uv run vmp devices                 # what is paired, and when it was last seen
uv run vmp revoke "George's iPhone"   # forget one; takes effect at once
```

Type the code into the app (the Pair screen after the URL test, or Settings, "Pair again").
The phone gets a long random token, kept in its keychain, and sends it with every request;
the Mac keeps only a fingerprint of it in `~/.config/voice-mode-proxy/devices.json`. The web
page pairs the same way and keeps the token in a cookie.

### How this stays private

- **Tailscale Serve (recommended).** The proxy binds to `127.0.0.1`, so nothing on any
  network can reach it directly. Serve forwards from your tailnet only, encrypted, to your
  own devices. Never use `tailscale funnel` for this: that is the public internet.
- **Your home WiFi, no Tailscale.** Set `host` in config.toml to the Mac's LAN address. That
  is plain HTTP: the pairing code, the token and your audio cross the WiFi unencrypted, and
  anyone on it can try a code. Only on a network you trust. The app refuses plain `http://`
  to anything but a private address (10.x, 192.168.x, .local, a Tailscale IP).
- **Exposed to the internet.** Don't. If you must, put a TLS reverse proxy such as Caddy in
  front of `127.0.0.1:8791` and never open the port itself.

## Configure

Settings come from `~/.config/voice-mode-proxy/config.toml` (or the file `VMP_CONFIG` names);
`config.example.toml` lists every key with its default. Any key can be overridden by an
environment variable, `VMP_` plus the key upper-cased. `projects` is the list of folders the
phone can start a session in; an entry like `~/Code/*` means every git repo under `Code`.

The speech rate, voice, VAD timings and the voice prompt can also be changed from the phone's
Settings screen while the server runs. Those choices are saved in `overrides.json` beside
`config.toml` and win over it until reset from the app (or the file is deleted).

## Test harness

```sh
uv run tools/ws_client.py -p "what is this project?"
uv run tools/ws_client.py --listen
```

## Docs

- `REQUIREMENTS.md`: goals and architecture.
- `BUILD-ORDER.md`: what was built, in what order.
- `CODE-REVIEW.md`: open and resolved review items.
- `BACKLOG.md`: server-side ideas not tied to the app.

## Releasing to GitHub

Daily work lives on the private Forgejo repo. GitHub only ever sees one commit per release,
pushed from this Mac with your own ssh key and `gh auth` by `scripts/publish-snapshot.sh`.

Each release:

```bash
pre-commit run --all-files
git tag -a v0.1.0          # the annotation becomes the GitHub release notes
git push origin v0.1.0
scripts/publish-snapshot.sh --dry-run   # tag is read from HEAD
scripts/publish-snapshot.sh
```

The script builds the tag's files minus `scripts/snapshot-exclude.txt` as one commit on top
of the previous release, refuses to ship if an internal string (see `forbidden` in the
script) survives or the working tree is dirty, then pushes `main` and the tag and creates
the GitHub release.

## Third-party software and licenses

This project is MIT. It stands on other people's work, under their terms:

| Component | Used for | License |
|---|---|---|
| [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (hexgrad) | the server voice; the ONNX files `install.sh` downloads are converted from these weights | Apache 2.0 |
| [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) (thewh1teagle) | runs the voice through onnxruntime | MIT |
| [phonemizer](https://github.com/bootphon/phonemizer) and [espeak-ng](https://github.com/espeak-ng/espeak-ng) | text to phonemes, pulled in by kokoro-onnx (`espeakng-loader` bundles `libespeak-ng`) | GPL-3.0 |
| [mlx-whisper](https://github.com/ml-explore/mlx-examples) (Apple) and the [Whisper](https://github.com/openai/whisper) weights (OpenAI) | speech recognition | MIT |
| [Silero VAD](https://github.com/snakers4/silero-vad) | deciding when you have stopped talking | MIT |
| onnxruntime, FastAPI, uvicorn, the Claude Agent SDK | the rest of the server | MIT |

Nothing here is redistributed by this repository: `uv sync` and `install.sh` fetch each
piece from its own source onto your Mac. The GPL parts matter only if someone ships a bundle
that contains them (an installer, a Docker image, a Homebrew bottle); that bundle would have
to go out under GPL terms. This repository does not do that, and the iOS app contains none
of them.

## Development

```sh
pre-commit install   # ruff format + lint, ty type check, gitleaks, whitespace
pre-commit run --all-files
```

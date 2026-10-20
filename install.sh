#!/bin/bash
# One-command install for the Voice Mode Proxy server on a Mac.
#
#   git clone https://github.com/CupOfGeo/voice-mode-proxy.git
#   cd voice-mode-proxy && ./install.sh
#
# Safe to run again: every step skips what is already there.
set -euo pipefail
cd "$(dirname "$0")"

KOKORO_BASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
WHISPER="mlx-community/whisper-large-v3-turbo"
CONFIG_DIR="$HOME/.config/voice-mode-proxy"
CONFIG="$CONFIG_DIR/config.toml"
PORT=8791

step() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] ||
  fail "Voice Mode Proxy needs a Mac with Apple Silicon: speech recognition runs on the Apple GPU through MLX."

step "1/6  uv (Python package manager)"
if command -v uv >/dev/null; then
  echo "already installed: $(uv --version)"
else
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

step "2/6  Python packages"
uv sync

step "3/6  Kokoro voice files (about 340 MB, once)"
mkdir -p voices/kokoro
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  if [ -s "voices/kokoro/$f" ]; then
    echo "have $f"
  else
    curl -L --fail --progress-bar -o "voices/kokoro/$f.part" "$KOKORO_BASE/$f" && mv "voices/kokoro/$f.part" "voices/kokoro/$f"
  fi
done

step "4/6  Whisper model (about 1.6 GB, once; later starts use the cached copy)"
uv run python -c "from huggingface_hub import snapshot_download; print(snapshot_download('$WHISPER'))"

step "5/6  Config file"
if [ -f "$CONFIG" ]; then
  echo "keeping $CONFIG"
else
  mkdir -p "$CONFIG_DIR"
  cat > "$CONFIG" <<EOF
# Voice Mode Proxy settings. config.example.toml in the repo lists every key.

# Only this Mac can reach the proxy directly; the phone comes in through Tailscale Serve
# (see below). Set host to your Tailscale IP to skip Serve, or "0.0.0.0" for the whole LAN.
host = "127.0.0.1"
port = $PORT

# Folders the phone can start a session in. "~/Code/*" means every git repo under ~/Code.
projects = ["~/Code/*"]
EOF
  echo "wrote $CONFIG"
fi

step "6/6  Claude Code and Tailscale"
ok=true
if command -v claude >/dev/null; then
  echo "Claude Code: $(claude --version 2>/dev/null | head -1)"
else
  ok=false
  cat <<'EOF'
Claude Code is not installed. The proxy drives it, so install it and log in once:
    curl -fsSL https://claude.ai/install.sh | bash
    claude          # follow the login prompt, then /exit
EOF
fi
TS=$(command -v tailscale || ls /Applications/Tailscale.app/Contents/MacOS/Tailscale 2>/dev/null || true)
if [ -n "$TS" ]; then
  echo "Tailscale: $("$TS" version 2>/dev/null | head -1)"
else
  ok=false
  echo "Tailscale is not installed. Get it from https://tailscale.com/download/mac on this Mac and on the phone (same account)."
fi

cat <<EOF

Done. To run the proxy:

    cd $(pwd)
    uv run vmp start        # installs it as a launchd agent and starts it; stays up across logins

"vmp start" prints a six-digit pairing code the first time; type it into the app. Later,
"uv run vmp pair" prints a fresh one, "uv run vmp devices" lists paired phones, "uv run vmp revoke NAME"
removes one. "uv run vmp status", "vmp logs", "vmp restart" and "vmp stop" do what they say.

Then, once per Mac, publish it on your tailnet over HTTPS (only devices on your Tailscale account can reach it):

    tailscale serve --bg --https=8443 http://127.0.0.1:$PORT

The URL to paste into the app's Settings screen is https://<this-mac>.<your-tailnet>.ts.net:8443
("tailscale serve status" prints it).
EOF
$ok || echo "Install the missing pieces above first."

# Backlog

Server-side work that is not part of the iOS plan (IOS-PLAN.md keeps the app's own list).
No order. Each becomes a step with a done condition when picked up.

1. **Replace the GPL phonemizer so the server can ship as a bundle.** kokoro-onnx turns
   text into phonemes through phonemizer and espeak-ng, both GPL-3 (see "Third-party
   software" in the README). That is fine for install-from-source, but a Docker image or
   a Homebrew bottle would contain them and would have to go out under GPL terms. George
   wants the whole server distributable under MIT-compatible terms; not because it will be
   sold, but to be fair to the licenses of what it uses (decided 2026-09-23).
   - Candidates: `misaki` (Apache 2.0, hexgrad's own G2P for Kokoro, used by the `kokoro`
     package and the `mlx-audio` port; its espeak fallback for unknown words is optional
     and must stay off), or a pure-Python English lexicon plus a small neural G2P for
     out-of-vocabulary words.
   - The swap is inside `tts.py` and the Kokoro tokenizer call; the voice files stay.
   - Acceptance: `uv pip list` shows nothing GPL, a `pip-licenses` check in pre-commit or
     CI keeps it that way, and spoken quality on the trail test is not worse (names,
     acronyms and file paths are the risk).
   - Then the bundle itself. A Dockerfile only serves text-only mode (no Apple GPU in a
     container), so the Homebrew formula is the real target.

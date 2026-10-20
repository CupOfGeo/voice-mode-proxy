"""Point the package at a throwaway config before anything imports it.

config.py builds `Settings()` at import time and server.py builds `Hub()` (which reads
overrides.json next to the config file), so VMP_CONFIG must be set before the first
`import voice_mode_proxy.server`. pytest loads this conftest before collecting the test
modules, which is early enough. Speech is off so no model loads; a bare
`TestClient(app)` (no `with`) never runs the lifespan anyway.
"""

import os
import tempfile
from pathlib import Path

_dir = Path(tempfile.mkdtemp(prefix="vmp-tests-"))
(_dir / "config.toml").write_text(
    f'stt_enabled = false\ntts_enabled = false\nlogs_dir = "{_dir / "logs"}"\nprojects = []\n'
)
os.environ["VMP_CONFIG"] = str(_dir / "config.toml")

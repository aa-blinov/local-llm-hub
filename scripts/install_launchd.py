#!/usr/bin/env python3
"""Autostart for Local LLM Hub via launchd.

  .venv/bin/python scripts/install_launchd.py            # install and start
  .venv/bin/python scripts/install_launchd.py --remove   # remove

One agent: the hub is always running (KeepAlive). The default model starts by itself
when "autostart": true is set in config/registry.json.
"""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "bin" / "python"
LABEL = "com.local.llm-hub"
AGENTS = Path.home() / "Library" / "LaunchAgents"
PLIST = AGENTS / f"{LABEL}.plist"
UID = os.getuid()


def launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def remove():
    launchctl("bootout", f"gui/{UID}", str(PLIST))
    if PLIST.exists():
        PLIST.unlink()
    print("Autostart removed.")


def install():
    AGENTS.mkdir(parents=True, exist_ok=True)
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [str(PY), "-m", "llm_hub"],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": True,
        "KeepAlive": True,
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
            "HOME": str(Path.home()),
        },
        "StandardOutPath": str(logs / "hub.out"),
        "StandardErrorPath": str(logs / "hub.out"),
    }
    with open(PLIST, "wb") as f:
        plistlib.dump(plist, f)
    if "--write-only" in sys.argv:
        # only write the agent file (called from the running panel, without a restart)
        print(f"Written: {PLIST}. The panel will start by itself after login.")
        return
    launchctl("bootout", f"gui/{UID}", str(PLIST))
    r = launchctl("bootstrap", f"gui/{UID}", str(PLIST))
    if r.returncode != 0:
        print("launchctl bootstrap:", r.stderr.strip() or r.stdout.strip())
        sys.exit(1)
    print(f"Installed: {PLIST}\nPanel: http://127.0.0.1:8765")


if __name__ == "__main__":
    remove() if "--remove" in sys.argv else install()

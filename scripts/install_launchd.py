#!/usr/bin/env python3
"""Автозапуск Local LLM Hub через launchd.

  .venv/bin/python scripts/install_launchd.py            # установить и запустить
  .venv/bin/python scripts/install_launchd.py --remove   # удалить

Один агент: хаб всегда поднят (KeepAlive). Модель по умолчанию стартует сама,
если в config/registry.json стоит "autostart": true.
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
    print("Автозапуск удалён.")


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
        # только записать файл агента (вызывается из работающей панели, без перезапуска)
        print(f"Записано: {PLIST}. Панель поднимется сама после входа в систему.")
        return
    launchctl("bootout", f"gui/{UID}", str(PLIST))
    r = launchctl("bootstrap", f"gui/{UID}", str(PLIST))
    if r.returncode != 0:
        print("launchctl bootstrap:", r.stderr.strip() or r.stdout.strip())
        sys.exit(1)
    print(f"Установлено: {PLIST}\nПанель: http://127.0.0.1:8765")


if __name__ == "__main__":
    remove() if "--remove" in sys.argv else install()

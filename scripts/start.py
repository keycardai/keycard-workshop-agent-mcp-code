"""Start the workshop: the requests MCP server and the agent, together.

start.bat (Windows) and start.command (macOS) run this file. The first run
creates .venv and installs the packages. Every run starts both processes,
opens the chat page, and keeps them running until this window closes.
"""

import os
import signal
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
INSTALLED = VENV / "installed"  # written only after a complete install
URL = "http://localhost:8484"


def install() -> None:
    print("First run: installing packages. This takes a minute or two.\n")
    if not PY.exists():
        venv.create(VENV, with_pip=True)
    pip = [PY, "-m", "pip", "install",
           "-r", "agent/requirements.txt", "-r", "mcp-requests/requirements.txt"]
    if subprocess.run(pip, cwd=ROOT).returncode != 0:
        sys.exit("\nInstalling packages failed. Read the messages above, "
                 "then see Troubleshooting in the workshop guide.")
    INSTALLED.touch()


def up() -> bool:
    try:
        urllib.request.urlopen(URL, timeout=1)
        return True
    except OSError:
        return False


def main() -> None:
    if sys.version_info < (3, 11):
        sys.exit(f"The workshop needs Python 3.11 or newer. "
                 f"This is Python {sys.version.split()[0]}.")
    if up():
        sys.exit(f"The workshop is already running at {URL}. "
                 "To restart it, close its window first, then start again.")
    if not INSTALLED.exists():
        install()

    # Closing the window or killing this script stops both processes too.
    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: sys.exit(0))

    procs = [
        subprocess.Popen([PY, "server.py"], cwd=ROOT / "mcp-requests"),
        subprocess.Popen([PY, "-m", "agent"], cwd=ROOT),
    ]
    try:
        # ponytail: polls the chat page for up to a minute, then gives up
        # on opening the browser; the processes keep running either way.
        for _ in range(60):
            if any(p.poll() is not None for p in procs):
                break
            if not up():
                time.sleep(1)
                continue
            print(f"\nWorkshop running. Chat at {URL}\n"
                  "To stop or restart, close this window.\n")
            webbrowser.open(URL)
            break
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        sys.exit("\nThe requests MCP server or the agent stopped. "
                 "Read the messages above, fix the cause, and start again.")
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()

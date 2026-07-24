"""Restore agent/ to a known-good checkpoint.

Usage:
    python scripts/restore_checkpoint.py [starter|ch03-agent-as-itself|ch04-user-login|ch05-on-behalf-of|finished]

Replaces the Python and HTML files in agent/ with the checkpoint's set; files
the checkpoint doesn't have are removed (e.g. restoring to starter removes
keycard/). Everything else in agent/ (.env included) is left alone.
"""

import shutil
import sys
from pathlib import Path

# What a shipped agent tree consists of. The internal repo's authoring check
# (check_parity.py) imports this from here so the two can never disagree.
TRACKED_SUFFIXES = (".py", ".html")

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "agent"
SOURCES = {
    "starter": ROOT / "checkpoints" / "starter",
    "ch03-agent-as-itself": ROOT / "checkpoints" / "ch03-agent-as-itself",
    "ch04-user-login": ROOT / "checkpoints" / "ch04-user-login",
    "ch05-on-behalf-of": ROOT / "checkpoints" / "ch05-on-behalf-of",
    "finished": ROOT / "agent-keycard",
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in SOURCES:
        names = " | ".join(SOURCES)
        print(f"usage: python scripts/restore_checkpoint.py [{names}]")
        return 1

    source = SOURCES[sys.argv[1]]
    wanted = {
        path.relative_to(source)
        for path in source.rglob("*")
        if path.suffix in TRACKED_SUFFIXES
    }

    for path in sorted(AGENT.rglob("*")):
        if path.suffix in TRACKED_SUFFIXES and path.relative_to(AGENT) not in wanted:
            path.unlink()
            print(f"  removed {path.relative_to(ROOT)}")
    for cache in AGENT.rglob("__pycache__"):
        shutil.rmtree(cache)
    for rel in sorted(wanted):
        target = AGENT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, target)
        print(f"  {target.relative_to(ROOT)}")

    for folder in sorted(AGENT.rglob("*"), reverse=True):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()

    print(f"agent/ restored to '{sys.argv[1]}'. Restart the agent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

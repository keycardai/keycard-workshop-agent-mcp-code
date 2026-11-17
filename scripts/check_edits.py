"""Compare your Chapter 2 edits with the finished files.

Run it from the workshop folder: python scripts/check_edits.py (python3 on
macOS and Linux). It changes nothing. Each file either matches the finished
version in mcp-requests-keycard/ or prints the lines that differ.
"""

import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ("server.py", "storage.py")


def lines(path: Path) -> list[str]:
    # splitlines() ignores the line-ending style, so an editor that saved
    # Windows line endings still compares equal.
    return path.read_text(encoding="utf-8").splitlines()


def main() -> int:
    differs = False
    for name in FILES:
        yours = lines(ROOT / "mcp-requests" / name)
        finished = lines(ROOT / "mcp-requests-keycard" / name)
        if yours == finished:
            print(f"mcp-requests/{name}: matches the finished file")
            continue
        differs = True
        print(f"mcp-requests/{name}: differs from mcp-requests-keycard/{name}")
        print("  Lines marked - are missing from your file; lines marked + should not be there.")
        diff = difflib.unified_diff(finished, yours, "finished", "yours", lineterm="", n=1)
        # ponytail: the first 40 lines of difference are enough to find a slip;
        # a file this far off is quicker to copy from mcp-requests-keycard/.
        for line in list(diff)[2:42]:
            print("  " + line)
    return 1 if differs else 0


if __name__ == "__main__":
    sys.exit(main())

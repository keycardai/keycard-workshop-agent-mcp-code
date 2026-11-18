"""Compare one chapter's edits with the finished files.

Run it from the workshop folder with the chapter number:
    python scripts/check_edits.py 5        (python3 on macOS and Linux)
It changes nothing. Each file either matches the finished version in
agent-keycard/ or mcp-requests-keycard/, or prints the lines that differ.
"""

import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The files each chapter edits. Every file is edited in exactly one chapter,
# so its finished version is the same path under the folder's -keycard twin.
CHAPTERS = {
    "2": ["mcp-requests/server.py", "mcp-requests/storage.py"],
    "4": ["agent/llm.py"],
    "5": ["agent/keycard/login.py", "agent/keycard/tokens.py", "agent/web.py"],
    "6": ["agent/tools/requests_queue.py"],
    "7": ["agent/review.py"],
}


def finished_path(name: str) -> str:
    folder, _, rest = name.partition("/")
    return f"{folder}-keycard/{rest}"


def lines(path: Path) -> list[str]:
    # Blank lines and trailing spaces never change what the code does, and
    # pasting a file together block by block rarely gets them identical.
    # splitlines() also ignores the line-ending style, so an editor that
    # saved Windows line endings still compares equal.
    return [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    chapter = sys.argv[1].lstrip("0") if len(sys.argv) == 2 else ""
    if chapter not in CHAPTERS:
        print(f"usage: python scripts/check_edits.py [{' | '.join(CHAPTERS)}]")
        print("Give the number of the chapter whose edits you want to check.")
        return 1

    differs = False
    for name in CHAPTERS[chapter]:
        reference = finished_path(name)
        if not (ROOT / name).exists():
            differs = True
            print(f"{name}: not found")
            continue
        yours = lines(ROOT / name)
        finished = lines(ROOT / reference)
        if yours == finished:
            print(f"{name}: matches the finished file")
            continue
        differs = True
        print(f"{name}: differs from {reference}")
        print("  Lines marked - are missing from your file; lines marked + should not be there.")
        diff = difflib.unified_diff(finished, yours, "finished", "yours", lineterm="", n=1)
        # ponytail: the first 40 lines of difference are enough to find a slip;
        # a file this far off is quicker to copy from the finished folder.
        # The @@ markers count lines without the blanks, so they would point
        # at the wrong line of the file; a gap marks each new spot instead.
        for line in list(diff)[2:42]:
            print("  ..." if line.startswith("@@") else "  " + line)
    return 1 if differs else 0


if __name__ == "__main__":
    sys.exit(main())

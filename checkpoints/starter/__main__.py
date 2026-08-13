import sys

from . import brief, check, web

if len(sys.argv) > 1 and sys.argv[1] == "check":
    raise SystemExit(check.main())

if len(sys.argv) > 1 and sys.argv[1] == "brief":
    raise SystemExit(brief.main())

web.serve()

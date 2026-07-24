import sys

from . import check, web

if len(sys.argv) > 1 and sys.argv[1] == "check":
    raise SystemExit(check.main())

web.serve()

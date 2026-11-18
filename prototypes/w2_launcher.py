"""Frozen prototype entry point with visible, file-backed startup diagnostics."""

import json
import sys
import traceback
from pathlib import Path


def launch():
    try:
        from prototypes.ads_cards_spike import main

        return main()
    except Exception:
        error = {"startup_error": traceback.format_exc(), "frozen": bool(
            getattr(sys, "frozen", False)
        )}
        if "--report" in sys.argv:
            path = Path(sys.argv[sys.argv.index("--report") + 1])
        else:
            path = Path(sys.executable).with_suffix(".error.json")
        path.write_text(json.dumps(error, indent=2), encoding="utf-8")
        if sys.stderr is not None:
            print(error["startup_error"], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(launch())

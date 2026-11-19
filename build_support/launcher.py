import sys
import traceback
from pathlib import Path


def launch():
    if "--map-worker" in sys.argv:
        from lodandsy.application.map_pyramid_worker import main
        return main(sys.argv[sys.argv.index("--map-worker") + 1:])
    if "--self-test" in sys.argv:
        from build_support.windows_smoke import main
    else:
        from lodandsy.main import main
    return main()


if __name__ == "__main__":
    try:
        raise SystemExit(launch())
    except Exception:
        report = Path(sys.executable).with_name("LODANDSY-startup-error.txt")
        if "--report" in sys.argv:
            report = Path(sys.argv[sys.argv.index("--report") + 1])
        report.write_text(traceback.format_exc(), encoding="utf-8")
        raise

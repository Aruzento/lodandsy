"""Prepare a local review artifact, notices and source; does not publish a release."""

import argparse
import hashlib
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".prototype-deps"
APP = CACHE / "dist/LODANDSY-W2-Preflight"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-licenses", action="store_true")
    args = parser.parse_args()
    licenses = CACHE / "license-texts"
    licenses.mkdir(exist_ok=True)
    for name in ["LGPL-3.0-only.txt", "GPL-3.0-only.txt"]:
        target = licenses / name
        if not target.exists() and args.fetch_licenses:
            url = f"https://raw.githubusercontent.com/qt/qtbase/v6.11.2/LICENSES/{name}"
            with urllib.request.urlopen(url, timeout=30) as response:
                target.write_bytes(response.read())
        if not target.exists():
            raise RuntimeError("Fetch the Qt license texts with --fetch-licenses first")
    if not (APP / "LODANDSY-W2-Preflight.exe").is_file():
        raise RuntimeError("Build the W2 prototype first")
    output_licenses = APP / "LICENSES"
    output_licenses.mkdir(exist_ok=True)
    for path in licenses.iterdir():
        if path.is_file():
            shutil.copy2(path, output_licenses / path.name)
    installed = CACHE / "build-venv/Lib/site-packages"
    shutil.copy2(installed / "PySide6QtAds/license/ads/LICENSE",
                 output_licenses / "Qt-ADS-LGPL-2.1.txt")
    shutil.copy2(installed / "pyside6_qtads-5.1.1.dist-info/licenses/LICENSE.txt",
                 output_licenses / "PySide6-QtAds-NOTICE.txt")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, output_licenses / "Python-LICENSE.txt")
    for name in ["README-W2.md", "THIRD-PARTY-W2.md", "requirements-w2-preflight.txt"]:
        shutil.copy2(ROOT / "prototypes" / name, APP / name)
    for package in ["lodandsy", "prototypes"]:
        for path in (ROOT / package).rglob("*.py"):
            target = APP / "source" / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    for name in ["w2_preflight.spec", "build_w2_preflight.ps1", "requirements-w2-preflight.txt"]:
        target = APP / "source/prototypes" / name
        shutil.copy2(ROOT / "prototypes" / name, target)
    archive = CACHE / "LODANDSY-W2-Preflight.zip"
    assert APP.resolve().is_relative_to(CACHE.resolve())
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in APP.rglob("*"):
            if path.is_file():
                bundle.write(path, str(Path(APP.name) / path.relative_to(APP)))
    print(archive)
    print("SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    print("Bytes", archive.stat().st_size)


if __name__ == "__main__":
    main()

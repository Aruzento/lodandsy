"""Create a local, reviewable portable candidate, including source and license notices."""

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".prototype-deps"
APP = CACHE / "mvp-dist/LODANDSY"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default="LODANDSY-MVP-Candidate.zip")
    args = parser.parse_args()
    if Path(args.archive).name != args.archive or not args.archive.endswith(".zip"):
        raise ValueError("Archive must be a ZIP filename inside .prototype-deps")
    if not (APP / "LODANDSY.exe").is_file():
        raise RuntimeError("Build the executable first")
    licenses = APP / "LICENSES"
    licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "build_support/SRD-5.1-NOTICE.txt", licenses / "SRD-5.1-NOTICE.txt")
    for path in (CACHE / "license-texts").glob("*.txt"):
        shutil.copy2(path, licenses / path.name)
    shutil.copytree(ROOT / "build_support/licenses", licenses / "libvips", dirs_exist_ok=True)
    import json

    provenance = json.loads((licenses / "libvips/Vips-provenance.json").read_text())
    native = next((APP / "_internal").glob("libvips-42-*.dll"))
    if hashlib.sha256(native.read_bytes()).hexdigest() != provenance["native_sha256"]:
        raise RuntimeError("Native libvips changed; repeat license/provenance verification")
    for name in ["LGPL-3.0-only.txt", "GPL-3.0-only.txt"]:
        if not (licenses / name).exists():
            raise RuntimeError("Supply Qt license texts; see build_support/README.md")
    import PySide6QtAds

    ads = Path(PySide6QtAds.__file__).parent
    shutil.copy2(ads / "license/ads/LICENSE", licenses / "Qt-ADS-LGPL-2.1.txt")
    sites = ads.parent
    shutil.copy2(
        sites / "pyside6_qtads-5.1.1.dist-info/licenses/LICENSE.txt",
        licenses / "PySide6-QtAds-NOTICE.txt",
    )
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", licenses / "Python-LICENSE.txt")
    for name in ["README.md", "THIRD-PARTY.md"]:
        shutil.copy2(ROOT / "build_support" / name, APP / name)
    # Include the exact application/build source, without private projects or local attachments.
    source = APP / "source"
    # Repackaging must not retain deleted editors/adapters from an earlier candidate.
    expected = CACHE.resolve() / "mvp-dist" / "LODANDSY" / "source"
    if source.resolve() != expected or not source.resolve().is_relative_to(CACHE.resolve()):
        raise RuntimeError("Unexpected source staging path")
    if source.exists():
        shutil.rmtree(source)
    for folder in ["lodandsy", "build_support", "tests", "docs", "prototypes"]:
        for path in (ROOT / folder).rglob("*"):
            if "references" in path.relative_to(ROOT).parts:
                continue
            # Pre-existing local proposal, superseded by ADR-033; not approved source.
            if path.relative_to(ROOT).as_posix() == (
                "docs/architecture/2026-11-21-cards-variables-audit.md"
            ):
                continue
            if path.is_file() and (
                path.suffix in {".py", ".md", ".spec", ".ps1", ".json", ".txt", ".drawio"}
                or path.is_relative_to(ROOT / "build_support/licenses")
                or (
                    path.suffix == ".png"
                    and any(
                        path.is_relative_to(ROOT / folder)
                        for folder in (
                            "docs/validation/2026-11-21-ui-acceptance",
                            "docs/validation/2026-11-22-character-sheet-v2",
                            "docs/validation/2026-11-25-polish",
                            "docs/validation/2026-11-25-map-m5",
                            "docs/validation/2026-11-25-map-m55",
                            "docs/validation/2026-11-26-map-m55-final",
                            "docs/validation/2026-11-26-tools-t3",
                            "docs/validation/2026-11-26-ui-system",
                            "docs/validation/2026-11-26-managed-projects",
                            "docs/validation/v001-followup",
                        )
                    )
                )
            ):
                target = source / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    for name in [
        "pyproject.toml",
        "requirements-runtime.lock",
        "requirements-dev.lock",
        "requirements-build.lock",
        "README.md",
        "AGENTS.md",
        "START-CODEX.md",
    ]:
        shutil.copy2(ROOT / name, source / name)
    shutil.copytree(ROOT / ".github", source / ".github", dirs_exist_ok=True)
    manifest = []
    for path in sorted(source.rglob("*")):
        if path.is_file():
            manifest.append(
                hashlib.sha256(path.read_bytes()).hexdigest()
                + "  "
                + path.relative_to(source).as_posix()
            )
    (source / "MANIFEST.sha256").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    archive = CACHE / args.archive
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(APP.rglob("*")):
            if path.is_file():
                bundle.write(path, str(Path("LODANDSY") / path.relative_to(APP)))
    print(archive)
    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        print("SHA256", checksum)
    archive.with_suffix(".zip.sha256").write_text(
        checksum + "  " + archive.name + "\n", encoding="ascii"
    )
    print("Bytes", archive.stat().st_size)


if __name__ == "__main__":
    main()

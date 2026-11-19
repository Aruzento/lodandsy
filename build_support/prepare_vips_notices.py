"""Import unmodified upstream notices after verifying the exact native DLL."""
import hashlib
import json
import tarfile
import zipfile
from importlib.metadata import distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    cache = ROOT / ".prototype-deps"
    destination = ROOT / "build_support/licenses"
    destination.mkdir(exist_ok=True)
    native = distribution("pyvips-binary")
    binary = next(native.locate_file(path) for path in native.files
                  if str(path).startswith("libvips-") and str(path).endswith(".dll"))
    checksum = hashlib.sha256(binary.read_bytes()).hexdigest()
    archive = cache / "libvips-8.18.7-win-x64.tar.gz"
    with tarfile.open(archive) as bundle:
        upstream = hashlib.sha256(bundle.extractfile("lib/libvips-42.dll").read()).hexdigest()
        if checksum != upstream:
            raise ValueError("Native DLL differs from the verified upstream distribution")
        for member, name in [("THIRD-PARTY-NOTICES.md", "Vips-THIRD-PARTY-NOTICES.md"),
                             ("versions.json", "Vips-versions.json")]:
            (destination / name).write_bytes(bundle.extractfile(member).read())
    sdk = cache / "vips-dev-x64-web-8.18.7-static-ffi.zip"
    with zipfile.ZipFile(sdk) as bundle:
        (destination / "Vips-LGPL-2.1.txt").write_bytes(bundle.read("vips-dev-8.18/LICENSE"))
    for package in ["pyvips", "pyvips-binary", "cffi", "pycparser"]:
        metadata = distribution(package)
        for path in metadata.files:
            if ".dist-info/licenses/" in str(path) and Path(path).name.startswith("LICENSE"):
                name = package + "-" + Path(path).name
                (destination / name).write_bytes(metadata.locate_file(path).read_bytes())
    provenance = {"native_sha256": checksum, "version": "8.18.7",
                  "binary_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                  "sdk_archive_sha256": hashlib.sha256(sdk.read_bytes()).hexdigest(),
                  "binary_archive_url": "https://github.com/kleisauke/libvips-packaging/"
                  "releases/download/v8.18.7/libvips-8.18.7-win-x64.tar.gz",
                  "sdk_archive_url": "https://github.com/libvips/build-win64-mxe/releases/"
                  "download/v8.18.7/vips-dev-x64-web-8.18.7-static-ffi.zip",
                  "native_sources_and_build": "https://github.com/libvips/build-win64-mxe/"
                  "tree/v8.18.7",
                  "packaging_sources": "https://github.com/kleisauke/libvips-packaging/"
                  "tree/v8.18.7"}
    (destination / "Vips-provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print("Verified native DLL SHA256", checksum)


if __name__ == "__main__":
    main()

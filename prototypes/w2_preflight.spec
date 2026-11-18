from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = collect_all("PySide6QtAds")
a = Analysis(
    [str(root / "prototypes/w2_launcher.py")],
    pathex=[str(root)], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[], excludes=[],
    noarchive=False, optimize=0,
)
# Qt 6.11.2 imports Windows' unversioned ICU API (System32/icuuc.dll -> icu.dll).
# PyInstaller collected an unrelated ICU-78 binary with suffixed exports instead.
# Keep the OS dependency; do not ship that incompatible replacement.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in {"icuuc.dll", "icudt78.dll"}]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="LODANDSY-W2-Preflight", debug=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=False, name="LODANDSY-W2-Preflight",
)

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = collect_all("PySide6QtAds")
vips_data, vips_binary, vips_hidden = collect_all("pyvips")
datas += vips_data
binaries += vips_binary
hiddenimports += vips_hidden + ["_libvips", "_cffi_backend"]
a = Analysis(
    [str(root / "build_support/launcher.py")], pathex=[str(root)],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[], runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
# Qt 6.11.2 uses Windows system ICU; the auto-discovered ICU78 has incompatible exports.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in {"icuuc.dll", "icudt78.dll"}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="LODANDSY",
          debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LODANDSY")

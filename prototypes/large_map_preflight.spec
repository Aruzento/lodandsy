"""Candidate only: use isolated map-preflight venv and existing locked Qt wheels."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
data, binary, hidden = collect_all("pyvips")
ads_data, ads_binary, ads_hidden = collect_all("PySide6QtAds")
a = Analysis([str(root / "prototypes/large_map_preflight.py")],
             pathex=[str(root)], binaries=binary + ads_binary,
             datas=data + ads_data, hiddenimports=hidden + ads_hidden + ["_libvips", "_cffi_backend"],
             hookspath=[], runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in {"icuuc.dll", "icudt78.dll"}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="LODANDSY-Map-Preflight-Qt",
          debug=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LODANDSY-Map-Preflight-Qt")

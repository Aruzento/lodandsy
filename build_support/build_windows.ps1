param([string]$Python = '.venv/Scripts/python.exe',
      [string]$Archive = 'LODANDSY-MVP-Candidate.zip')
$ErrorActionPreference = 'Stop'
$buildRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $buildRoot
try {
    & $Python -c 'import sys; assert sys.version_info[:3] == (3,14,8), sys.version'
    if ($LASTEXITCODE -ne 0) { throw 'Build requires CPython 3.14.8 x64.' }
    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
    & $Python -m PyInstaller --clean --noconfirm --distpath .prototype-deps/mvp-dist `
        --workpath .prototype-deps/mvp-build build_support/windows.spec
    if ($LASTEXITCODE -ne 0) { throw 'Windows build failed.' }
    & $Python -m build_support.verify_frozen --report .prototype-deps/iteration3-frozen-source.json
    if ($LASTEXITCODE -ne 0) { throw 'Frozen source verification failed.' }
    & $Python -m build_support.package_windows --archive $Archive
    if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
} finally {
    Pop-Location
}

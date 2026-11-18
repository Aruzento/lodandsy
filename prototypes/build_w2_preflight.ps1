$ErrorActionPreference = 'Stop'
$prototypeRoot = Split-Path -Parent $PSScriptRoot
$prototypePython = Join-Path $prototypeRoot '.prototype-deps/build-venv/Scripts/python.exe'
$prototypeDist = Join-Path $prototypeRoot '.prototype-deps/dist'
$prototypeWork = Join-Path $prototypeRoot '.prototype-deps/build-work'
if (-not (Test-Path -LiteralPath $prototypePython)) {
    throw 'Create .prototype-deps/build-venv and install requirements-w2-preflight.txt first.'
}
& $prototypePython -c 'import sys; assert sys.version_info[:3] == (3, 14, 8), sys.version'
if ($LASTEXITCODE -ne 0) { throw 'Expected Python 3.14.8.' }
Push-Location -LiteralPath $prototypeRoot
try {
    & $prototypePython -m PyInstaller --noconfirm `
        --distpath $prototypeDist --workpath $prototypeWork prototypes/w2_preflight.spec
    if ($LASTEXITCODE -ne 0) { throw 'W2 build failed.' }
} finally {
    Pop-Location
}

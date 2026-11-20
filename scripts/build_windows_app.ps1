$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "This build requires Windows." }
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$Venv = Join-Path $Root ".build-venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) { & $Python -m venv $Venv; if ($LASTEXITCODE -ne 0) { throw "venv creation failed" } }
& $VenvPython -m pip install -e "$Root[build]"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
& $VenvPython -c "from PySide6.QtWebEngineWidgets import QWebEngineView"
if ($LASTEXITCODE -ne 0) { throw "Qt WebEngine unavailable" }
& $VenvPython -m PyInstaller --noconfirm --distpath "$Root\dist" --workpath "$Root\build\windows" "$Root\packaging\windows\TrialCruncher.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$BundleName = (& $VenvPython "$Root\scripts\version_metadata.py" --field bundle_app_name).Trim()
Copy-Item "$Root\dist\trial-cruncher-cli.exe" "$Root\dist\$BundleName\trial-cruncher-cli.exe" -Force

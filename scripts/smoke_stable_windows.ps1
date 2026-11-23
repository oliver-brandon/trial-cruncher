# Run only on a disposable GitHub-hosted Windows runner. Installs the candidate
# on a first release, or upgrades a supplied previous stable installer.
param(
    [Parameter(Mandatory = $true)][string]$CandidateDirectory,
    [Parameter(Mandatory = $true)][string]$CandidateVersion,
    [string]$PreviousInstaller = "",
    [string]$PreviousVersion = ""
)
$ErrorActionPreference = "Stop"
if ($env:GITHUB_ACTIONS -ne "true" -or $env:RUNNER_OS -ne "Windows" -or -not $env:RUNNER_TEMP) {
    throw "Run this smoke check only on an ephemeral GitHub-hosted Windows runner."
}
if ([bool]$PreviousInstaller -ne [bool]$PreviousVersion) {
    throw "Provide both PreviousInstaller and PreviousVersion, or neither."
}
$install = Join-Path $env:RUNNER_TEMP "trial-stable-upgrade"
if (Test-Path -LiteralPath $install) { throw "Smoke test installation path already exists." }
$CandidateDirectory = (Resolve-Path -LiteralPath $CandidateDirectory).Path
$feed = Get-Content (Join-Path $CandidateDirectory "releases.stable-win-x64.json") -Raw | ConvertFrom-Json
$assets = @($feed.Assets | Where-Object {
    $_.Version -eq $CandidateVersion -and $_.Type -eq "Full" -and $_.PackageId -eq "com.trialcruncher.app"
})
if ($assets.Count -ne 1) { throw "Candidate feed must contain exactly one matching stable full package." }
$filename = [string]$assets[0].FileName
if ([IO.Path]::GetFileName($filename) -ne $filename) { throw "Invalid package filename." }
$package = Join-Path $CandidateDirectory $filename
if (-not (Test-Path -LiteralPath $package -PathType Leaf)) { throw "Candidate package is missing." }
if ((Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash -ne $assets[0].SHA256) {
    throw "Candidate package hash mismatch."
}
$setups = @(Get-ChildItem -LiteralPath $CandidateDirectory -Filter "*-Setup.exe" -File)
if ($setups.Count -ne 1) { throw "Expected exactly one candidate installer." }
$setup = if ($PreviousInstaller) { (Resolve-Path -LiteralPath $PreviousInstaller).Path } else { $setups[0].FullName }
$initialVersion = if ($PreviousInstaller) { $PreviousVersion } else { $CandidateVersion }
$exe = Join-Path $install "current\Trial Cruncher.exe"
$updater = Join-Path $install "Update.exe"
$proc = $null
$old = $null
$apply = $null
$restarted = $null
$reopened = $null
$candidateProc = $null
$candidateApp = $null
$candidateInstall = Join-Path $env:RUNNER_TEMP "trial-fresh-candidate"

function Assert-InstalledIdentity([string]$version) {
    $manifestPath = Join-Path $install "current\sq.version"
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw "Installed package manifest is missing." }
    [xml]$manifest = Get-Content -LiteralPath $manifestPath -Raw
    $id = $manifest.SelectSingleNode("//*[local-name()='metadata']/*[local-name()='id']")
    $installedVersion = $manifest.SelectSingleNode("//*[local-name()='metadata']/*[local-name()='version']")
    if (-not $id -or -not $installedVersion -or $id.InnerText -ne "com.trialcruncher.app" -or $installedVersion.InnerText -ne $version) {
        throw "Installed package identity or version is incorrect; expected com.trialcruncher.app $version."
    }
}

function Wait-ForWindow([string]$path, [int]$seconds = 90) {
    $until = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $until) {
        $found = Get-Process -Name "Trial Cruncher" -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -eq $path -and $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -eq "Trial Cruncher" } |
            Select-Object -First 1
        if ($found) { return $found }
        Start-Sleep -Milliseconds 500
    }
    throw "Installed Trial Cruncher did not open its main window."
}

try {
    $proc = Start-Process -FilePath $setup -ArgumentList @("--silent", "--installto", ('"' + $install + '"')) -PassThru
    if (-not $proc.WaitForExit(180000)) { throw "Installer did not finish." }
    if ($proc.ExitCode -ne 0) { throw "Installer returned $($proc.ExitCode)." }
    if (-not (Test-Path -LiteralPath $updater) -or -not (Test-Path -LiteralPath $exe)) {
        throw "Installation lacks the expected updater or application executable."
    }
    Assert-InstalledIdentity $initialVersion
    $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $null
    foreach ($link in @(Get-ChildItem -Path $startMenu -Filter "*.lnk" -Recurse -ErrorAction SilentlyContinue)) {
        $target = $shell.CreateShortcut($link.FullName).TargetPath
        if ($target -eq $exe -or $target -eq (Join-Path $install "Trial Cruncher.exe")) {
            $shortcut = $link.FullName
            break
        }
    }
    if (-not $shortcut) { throw "Installed Start Menu shortcut not found." }
    $old = Start-Process -FilePath $exe -PassThru
    $old = Wait-ForWindow $exe
    if ($PreviousInstaller) {
        $apply = Start-Process -FilePath $updater -ArgumentList @("--silent", "apply", "--waitPid", $old.Id, "--package", ('"' + $package + '"')) -PassThru
        $old.CloseMainWindow() | Out-Null
        if (-not $old.WaitForExit(30000)) { throw "Previous application did not close." }
        if (-not $apply.WaitForExit(180000)) { throw "Updater did not finish." }
        if ($apply.ExitCode -ne 0) { throw "Updater returned $($apply.ExitCode)." }
        Assert-InstalledIdentity $CandidateVersion
        $restarted = Wait-ForWindow $exe
        $restarted.CloseMainWindow() | Out-Null
        if (-not $restarted.WaitForExit(30000)) { throw "Updated application did not close." }
    } else {
        $old.CloseMainWindow() | Out-Null
        if (-not $old.WaitForExit(30000)) { throw "Application did not close." }
    }
    if (-not (Test-Path -LiteralPath $shortcut)) { throw "Start Menu shortcut disappeared." }
    $target = $shell.CreateShortcut($shortcut).TargetPath
    if (-not (Test-Path -LiteralPath $target)) { throw "Start Menu shortcut target no longer exists." }
    Start-Process -FilePath $shortcut
    $reopened = Wait-ForWindow $exe
    $reopened.CloseMainWindow() | Out-Null
    if (-not $reopened.WaitForExit(30000)) { throw "Shortcut-launched application did not close." }
    if (-not (Test-Path -LiteralPath (Join-Path $install "current\trial-cruncher-cli.exe"))) {
        throw "Installed command-line executable is missing."
    }
    # When an earlier installer was used for the upgrade test, verify the
    # candidate setup executable in a separate installation directory too.
    if ($PreviousInstaller) {
        if (Test-Path -LiteralPath $candidateInstall) { throw "Candidate install path already exists." }
        $candidateProc = Start-Process -FilePath $setups[0].FullName -ArgumentList @("--silent", "--installto", ('"' + $candidateInstall + '"')) -PassThru
        if (-not $candidateProc.WaitForExit(180000)) { throw "Candidate installer did not finish." }
        if ($candidateProc.ExitCode -ne 0) { throw "Candidate installer returned $($candidateProc.ExitCode)." }
        $candidateExe = Join-Path $candidateInstall "current\Trial Cruncher.exe"
        $candidateManifest = Join-Path $candidateInstall "current\sq.version"
        if (-not (Test-Path -LiteralPath $candidateExe) -or -not (Test-Path -LiteralPath $candidateManifest)) {
            throw "Candidate installer did not create the expected application and manifest."
        }
        [xml]$candidateInfo = Get-Content -LiteralPath $candidateManifest -Raw
        $candidateId = $candidateInfo.SelectSingleNode("//*[local-name()='metadata']/*[local-name()='id']")
        $candidateVer = $candidateInfo.SelectSingleNode("//*[local-name()='metadata']/*[local-name()='version']")
        if (-not $candidateId -or -not $candidateVer -or $candidateId.InnerText -ne "com.trialcruncher.app" -or $candidateVer.InnerText -ne $CandidateVersion) {
            throw "Candidate installer package identity or version is incorrect."
        }
        & .build-venv/Scripts/python.exe scripts/smoke_installed_gui.py $candidateExe
        if ($LASTEXITCODE -ne 0) { throw "Candidate installer GUI verification failed." }
        $candidateCli = Join-Path $candidateInstall "current\trial-cruncher-cli.exe"
        & .build-venv/Scripts/python.exe scripts/smoke_packaged_analysis.py $candidateCli
        if ($LASTEXITCODE -ne 0) { throw "Candidate installer CLI verification failed." }
        $candidateApp = Start-Process -FilePath $candidateExe -PassThru
        $candidateApp = Wait-ForWindow $candidateExe
        $candidateApp.CloseMainWindow() | Out-Null
        if (-not $candidateApp.WaitForExit(30000)) { throw "Candidate installer app did not close." }
    }
    Write-Host "Verified candidate installer, installed identity, startup, shortcut, and candidate version $CandidateVersion."
} finally {
    $owned = @(Get-Process -Name "Trial Cruncher", "Update" -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -and $_.Path.StartsWith("$install\", [StringComparison]::OrdinalIgnoreCase)
    })
    foreach ($process in @($proc, $old, $apply, $restarted, $reopened, $candidateProc, $candidateApp) + $owned) {
        if ($null -ne $process) {
            try {
                $process.Refresh()
                if (-not $process.HasExited -and ($process.Path -eq $setup -or $process.Path -eq $setups[0].FullName -or $process.Path.StartsWith("$install\", [StringComparison]::OrdinalIgnoreCase) -or $process.Path.StartsWith("$candidateInstall\", [StringComparison]::OrdinalIgnoreCase))) {
                    $process.Kill()
                    $process.WaitForExit(5000) | Out-Null
                }
            } catch { Write-Warning "Could not stop smoke-test process $($process.Id): $_" }
        }
    }
}

# Signal success explicitly to the calling workflow after cleanup.
exit 0
